"""Stage 4 long-lived federated node.

One process imports TensorFlow once, loads its own year of data once, publishes
retained online status, waits for round invitations, and runs this node DAG::

    receive_model -> evaluate -> local_train -> upload

The process never publishes raw readings.  The only upload is the float32
weight vector, checksums, and validation scalars (``val_loss``, ``n_val``,
``n_samples``).  ``--inference-only`` (used by node5/the phone) never imports
TensorFlow and never uploads weights.
"""

from __future__ import annotations

import argparse
import logging
import queue
import signal
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import paho.mqtt.client as mqtt

from common.config import (
    inference_only_node_ids,
    load_config,
    resolve_path,
    training_node_ids,
)
from common.federated import is_newer_version
from common.model_delivery import GlobalModelReceiver, ReceivedModel
from common.mqtt_utils import (
    configure_last_will,
    create_client,
    loads,
    node_topic,
    publish_json,
    reason_code_value,
)
from common.weight_transfer import (
    build_chunk_message,
    build_transfer_metadata,
    encode_weights,
    global_announce_topic,
    global_chunk_filter,
    round_ack_filter,
    round_start_filter,
    round_update_chunk_topic,
    round_update_meta_topic,
    split_weight_payload,
    validate_header,
)
from node.node_client import make_health, make_status
from server.dag_runner import DAG, Task, run_dag

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


class NodeRoundError(RuntimeError):
    """Raised when one node-side round cannot continue."""


class FederatedNode:
    """MQTT node that trains on its own data and uploads only weights."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        node_id: str,
        host: str | None = None,
        port: int | None = None,
        seed: int | None = None,
        window_hours: int = 24,
        inference_only: bool = False,
        dummy: bool = False,
        dummy_value: float = 1.0,
        dummy_samples: int = 100,
        dummy_count: int = 9025,
        upload_delay: float = 0.0,
        ack_timeout: float = 30.0,
        keepalive: int = 30,
        run_seconds: float | None = None,
    ) -> None:
        self.config = load_config(config_path)
        if node_id not in self.config.get("nodes", {}):
            raise ValueError(
                f"unknown node_id {node_id!r}; "
                f"expected one of {sorted(self.config.get('nodes', {}))}"
            )
        mqtt_cfg = self.config.get("mqtt", {})
        self.node_id = node_id
        self.host = str(host or mqtt_cfg.get("host", "127.0.0.1"))
        self.port = int(port or mqtt_cfg.get("port", 1883))
        self.qos = int(mqtt_cfg.get("qos", 1))
        self.base_topic = str(mqtt_cfg.get("base_topic", "aq"))
        self.chunk_size = int(mqtt_cfg.get("chunk_size", 16384))
        self.heartbeat_sec = float(mqtt_cfg.get("heartbeat_sec", 10))
        self.keepalive = int(keepalive)
        self.seed = int(seed if seed is not None else self.config.get("seed", 42))
        self.window_hours = int(window_hours)
        self.inference_only = bool(
            inference_only or node_id in inference_only_node_ids(self.config)
        )
        if not self.inference_only and node_id not in training_node_ids(self.config):
            raise ValueError(f"{node_id!r} is not a training node")
        self.dummy = bool(dummy)
        self.dummy_value = float(dummy_value)
        self.dummy_samples = int(dummy_samples)
        self.dummy_count = int(dummy_count)
        self.upload_delay = float(upload_delay)
        self.ack_timeout = float(ack_timeout)
        self.run_seconds = run_seconds

        self.status_topic = node_topic(self.base_topic, self.node_id, "status")
        self.health_topic = node_topic(self.base_topic, self.node_id, "health")

        self.client: mqtt.Client | None = None
        self._inbox: queue.Queue[tuple[str, bytes]] = queue.Queue()
        self._rounds: queue.Queue[dict[str, Any]] = queue.Queue()
        self._connected = threading.Event()
        self._global_receiver = GlobalModelReceiver(self.base_topic)
        self._global_model: ReceivedModel | None = None
        self._global_lock = threading.Lock()
        self._ack_events: dict[tuple[int, str], threading.Event] = {}
        self._ack_results: dict[tuple[int, str], dict[str, Any]] = {}
        self._ack_lock = threading.Lock()
        self._seen_rounds: set[int] = set()
        self._seen_lock = threading.Lock()

        self.model_config: dict[str, Any] = {}
        self.model: Any = None
        self.prepared: dict[str, Any] | None = None
        self._training_ready = False

    # ------------------------------------------------------------------ setup
    def _load_training_state(self) -> None:
        if self.dummy:
            self.model_config = {}
            self._training_ready = True
            return
        from common.improved import improved_model_config, prepare_improved_node
        from common.model import build_model_from_config
        from common.preprocess import load_raw

        if "scaler" not in self.config or "dataset_path" not in self.config:
            raise ValueError("config.json needs dataset_path and scaler")
        raw = load_raw(resolve_path(self.config["dataset_path"]))
        year = int(self.config["nodes"][self.node_id])
        self.prepared = prepare_improved_node(
            raw,
            node_id=self.node_id,
            year=year,
            scaler=self.config["scaler"],
            features=list(self.config["features"]),
            window_hours=self.window_hours,
            horizon=1,
            delta=True,
            cyclic_hour=True,
            train_fraction=float(self.config["train_fraction"]),
            val_fraction_of_train=float(self.config["val_fraction_of_train"]),
        )
        self.model_config = improved_model_config(
            self.config, window_hours=self.window_hours, seed=self.seed
        )
        self.model = build_model_from_config(self.model_config)
        self._training_ready = True
        print(
            f"{self.node_id} ready: year={year} "
            f"train={len(self.prepared['X_train'])} "
            f"val={len(self.prepared['X_val'])} "
            f"test={len(self.prepared['X_test'])} "
            f"parameters={int(self.model.count_params())}",
            flush=True,
        )

    # ------------------------------------------------------------------- MQTT
    def _connect(self) -> None:
        self.client = create_client(
            f"node-{self.node_id}", self.host, self.port, keepalive=self.keepalive
        )
        configure_last_will(
            self.client,
            self.status_topic,
            make_status(self.node_id, "offline", "lwt"),
            qos=self.qos,
            retain=True,
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        backoff = 1.0
        while not STOP.is_set():
            try:
                self.client.connect(self.host, self.port, self.keepalive)
                break
            except OSError as exc:
                LOGGER.warning(
                    "broker unavailable at %s:%s (%s); retry in %.1fs",
                    self.host,
                    self.port,
                    exc,
                    backoff,
                )
                STOP.wait(backoff)
                backoff = min(backoff * 2.0, 30.0)
        if STOP.is_set():
            raise NodeRoundError("stopped before connecting")
        self.client.loop_start()
        if not self._connected.wait(timeout=10.0):
            raise NodeRoundError("MQTT connection was not confirmed")
        publish_json(
            self.client,
            self.status_topic,
            make_status(self.node_id, "online"),
            qos=self.qos,
            retain=True,
        )
        print(
            f"{self.node_id} online at {self.host}:{self.port} "
            f"inference_only={self.inference_only}",
            flush=True,
        )

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        if reason_code_value(reason_code) != 0:
            LOGGER.error("connect failed: %s", reason_code)
            return
        LOGGER.info("connected to %s:%s as %s", self.host, self.port, self.node_id)
        topics = [
            (global_announce_topic(self.base_topic), self.qos),
            (global_chunk_filter(self.base_topic), self.qos),
            (round_start_filter(self.base_topic), self.qos),
        ]
        if not self.inference_only:
            topics.append((round_ack_filter(self.base_topic, self.node_id), self.qos))
        client.subscribe(topics)
        self._connected.set()

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        del client, userdata
        self._inbox.put((message.topic, bytes(message.payload)))

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, *args: Any) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        code = reason_code_value(reason_code) if reason_code is not None else None
        if code == 0:
            LOGGER.info("disconnected cleanly")
        else:
            LOGGER.warning("disconnected unexpectedly (%s); paho will reconnect", reason_code)

    def _drain_inbox(self) -> None:
        while True:
            try:
                topic, payload = self._inbox.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle_message(topic, payload)
            except Exception:  # pragma: no cover - keep the node alive
                LOGGER.exception("unexpected message failure on %s", topic)

    def _handle_message(self, topic: str, payload: bytes) -> None:
        if topic == global_announce_topic(self.base_topic) or "/global/chunk/" in topic:
            result = self._global_receiver.handle_message(topic, payload)
            if result is not None:
                self._accept_global_model(result)
            return
        if topic.endswith("/start"):
            self._handle_round_start(payload)
            return
        if topic.endswith(f"/ack/{self.node_id}"):
            self._handle_ack(payload)

    def _accept_global_model(self, model: ReceivedModel) -> None:
        metadata = model.metadata
        if not self.dummy:
            received_config = metadata.get("model") or {}
            for key in ("window_hours", "n_features", "pool_size"):
                if key not in received_config:
                    print(
                        f"{self.node_id} ignoring global model without {key}",
                        flush=True,
                    )
                    return
            if int(received_config["window_hours"]) != self.window_hours:
                print(
                    f"{self.node_id} ignoring global model window="
                    f"{received_config['window_hours']} (expected {self.window_hours})",
                    flush=True,
                )
                return
        with self._global_lock:
            self._global_model = model
        print(
            f"{self.node_id} received global model "
            f"{metadata['model_version']} size={metadata['size']}",
            flush=True,
        )

    def _handle_round_start(self, payload: bytes) -> None:
        try:
            message = loads(payload)
            validate_header(message, expected_node_id="flserver")
            if message.get("message_type") != "round_start":
                raise ValueError("not a round_start message")
            round_number = int(message["round"])
            selected = list(message.get("selected_nodes") or [])
            model_version = str(message["model_version"])
            deadline_ts = float(message["deadline_ts"])
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("bad round start: %s", exc)
            return
        if self.node_id not in selected:
            print(
                f"{self.node_id} not selected for round {round_number}; skipping",
                flush=True,
            )
            return
        if self.inference_only:
            print(
                f"{self.node_id} inference-only: saw round {round_number} "
                f"model={model_version}; not training",
                flush=True,
            )
            return
        with self._seen_lock:
            if round_number in self._seen_rounds:
                return
            self._seen_rounds.add(round_number)
        message["_deadline_ts"] = deadline_ts
        print(
            f"{self.node_id} invited to round {round_number} "
            f"model={model_version} local_epochs={message.get('local_epochs')}",
            flush=True,
        )
        self._rounds.put(message)

    def _handle_ack(self, payload: bytes) -> None:
        try:
            ack = loads(payload)
            validate_header(ack)
            if ack.get("message_type") != "ack":
                raise ValueError("not an ack")
            if ack.get("target_node") != self.node_id:
                raise ValueError("ack target_node mismatch")
            key = (int(ack["round"]), str(ack["sha256"]))
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("bad ack: %s", exc)
            return
        with self._ack_lock:
            self._ack_results[key] = ack
            event = self._ack_events.get(key)
        if event is not None:
            event.set()

    # ------------------------------------------------------------- node DAG
    def _wait_for_global_model(
        self, version: str, deadline_ts: float
    ) -> ReceivedModel:
        deadline = min(time.time() + 30.0, deadline_ts)
        while not STOP.is_set() and time.time() < deadline:
            with self._global_lock:
                model = self._global_model
            if model is not None:
                current = str(model.metadata["model_version"])
                if current == version:
                    return model
                if is_newer_version(current, version):
                    raise NodeRoundError(
                        f"round model {version} is stale; latest is {current}"
                    )
            STOP.wait(0.05)
        raise NodeRoundError(f"global model {version} was not received before the deadline")

    def _task_receive_model(self, context: dict[str, Any]) -> dict[str, Any]:
        invitation = context["invitation"]
        version = str(invitation["model_version"])
        if self.dummy:
            with self._global_lock:
                model = self._global_model
            if model is not None and model.metadata["model_version"] == version:
                context["global_model"] = model
            else:
                context["global_model"] = None
            return {}
        context["global_model"] = self._wait_for_global_model(
            version, float(invitation["_deadline_ts"])
        )
        return {}

    def _task_evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        if self.dummy:
            return {
                "val_loss": abs(self.dummy_value),
                "n_val": self.dummy_samples,
            }
        if self.model is None or self.prepared is None:
            raise NodeRoundError("training state is not loaded")
        from common.model import unflatten_weights

        global_model: ReceivedModel = context["global_model"]
        unflatten_weights(self.model, global_model.weights)
        metrics = self.model.evaluate(
            self.prepared["X_val"],
            self.prepared["y_val"],
            batch_size=int(self.config["model"].get("batch_size", 64)),
            verbose=0,
            return_dict=True,
        )
        return {
            "val_loss": float(metrics["loss"]),
            "n_val": len(self.prepared["y_val"]),
        }

    def _task_local_train(self, context: dict[str, Any]) -> dict[str, Any]:
        invitation = context["invitation"]
        if self.dummy:
            weights = np.full(self.dummy_count, self.dummy_value, dtype=np.float32)
            return {
                "weights": weights,
                "n_samples": self.dummy_samples,
                "dummy": True,
            }
        if self.model is None or self.prepared is None:
            raise NodeRoundError("training state is not loaded")
        import tensorflow as tf

        from common.model import flatten_weights, set_seed

        round_number = int(invitation["round"])
        set_seed(self.seed + 1000 * round_number + int(self.node_id.removeprefix("node")))
        learning_rate = float(
            invitation.get("learning_rate", self.model_config.get("learning_rate", 0.001))
        )
        self.model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
            loss="mse",
            metrics=["mae"],
        )
        self.model.fit(
            self.prepared["X_train"],
            self.prepared["y_train"],
            epochs=int(invitation.get("local_epochs", 1)),
            batch_size=int(self.config["model"].get("batch_size", 64)),
            shuffle=True,
            verbose=0,
        )
        return {
            "weights": flatten_weights(self.model),
            "n_samples": len(self.prepared["y_train"]),
        }

    def _task_upload(self, context: dict[str, Any]) -> dict[str, Any]:
        invitation = context["invitation"]
        round_number = int(invitation["round"])
        if time.time() > float(invitation["_deadline_ts"]):
            raise NodeRoundError("round deadline passed before upload")
        if self.upload_delay > 0:
            STOP.wait(self.upload_delay)
        if time.time() > float(invitation["_deadline_ts"]):
            raise NodeRoundError("round deadline passed before upload")
        if self.client is None:
            raise NodeRoundError("MQTT client is not connected")

        weights = np.asarray(context["weights"], dtype=np.float32)
        kind = "dummy" if context.get("dummy") else "model"
        metadata = build_transfer_metadata(
            weights,
            node_id=self.node_id,
            model_version=str(invitation["model_version"]),
            model_config={} if kind == "dummy" else self.model_config,
            kind=kind,
            round_number=round_number,
            chunk_size=self.chunk_size,
        )
        metadata.update(
            {
                "n_samples": int(context["n_samples"]),
                "n_val": int(context["n_val"]),
                "val_loss": float(context["val_loss"]),
                "local_epochs": int(invitation.get("local_epochs", 1)),
                "learning_rate": float(invitation.get("learning_rate", 0.001)),
            }
        )
        payload = encode_weights(weights)
        chunks = split_weight_payload(payload, self.chunk_size)
        key = (round_number, str(metadata["sha256"]))
        event = threading.Event()
        with self._ack_lock:
            self._ack_events[key] = event
            self._ack_results.pop(key, None)
        try:
            info = publish_json(
                self.client,
                round_update_meta_topic(self.base_topic, round_number, self.node_id),
                metadata,
                qos=self.qos,
                retain=False,
            )
            info.wait_for_publish(timeout=10.0)
            for index, chunk in enumerate(chunks):
                message = build_chunk_message(metadata, index, chunk)
                info = publish_json(
                    self.client,
                    round_update_chunk_topic(
                        self.base_topic, round_number, self.node_id, index
                    ),
                    message,
                    qos=self.qos,
                    retain=False,
                )
                info.wait_for_publish(timeout=10.0)
            print(
                f"{self.node_id} uploaded round {round_number} "
                f"version={metadata['model_version']} size={metadata['size']} "
                f"chunks={len(chunks)} n_samples={metadata['n_samples']} "
                f"val_loss={metadata['val_loss']:.6f}",
                flush=True,
            )
            remaining = max(
                1.0, min(self.ack_timeout, float(invitation["_deadline_ts"]) - time.time())
            )
            if not event.wait(timeout=remaining):
                print(
                    f"{self.node_id} round {round_number} ack timeout",
                    flush=True,
                )
                return {"ack": None}
            with self._ack_lock:
                ack = self._ack_results.pop(key, None)
            status = None if ack is None else ack.get("status")
            print(
                f"{self.node_id} round {round_number} ack={status} "
                f"reason={None if ack is None else ack.get('reason')}",
                flush=True,
            )
            return {"ack": ack}
        finally:
            with self._ack_lock:
                self._ack_events.pop(key, None)

    def _run_node_round(self, invitation: dict[str, Any]) -> bool:
        dag = DAG(
            [
                Task("receive_model", self._task_receive_model, timeout=35.0),
                Task(
                    "evaluate",
                    self._task_evaluate,
                    depends_on=("receive_model",),
                    timeout=120.0,
                ),
                Task(
                    "local_train",
                    self._task_local_train,
                    depends_on=("evaluate",),
                    timeout=300.0,
                ),
                Task(
                    "upload",
                    self._task_upload,
                    depends_on=("local_train",),
                    timeout=max(60.0, self.upload_delay + 60.0),
                ),
            ]
        )
        result = run_dag(dag, context={"invitation": invitation}, logger=LOGGER)
        if not result.success:
            failed = [
                f"{name}: {task.error}"
                for name, task in result.tasks.items()
                if task.status == "failed"
            ]
            print(
                f"{self.node_id} round {invitation.get('round')} failed: "
                f"{'; '.join(failed)}",
                flush=True,
            )
        return result.success

    def _worker_loop(self) -> None:
        while not STOP.is_set():
            try:
                invitation = self._rounds.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._run_node_round(invitation)
            except Exception:  # pragma: no cover - keep the long-lived node alive
                LOGGER.exception("node round failed")

    # ------------------------------------------------------------------- run
    def _publish_heartbeat(self) -> None:
        if self.client is None:
            return
        publish_json(
            self.client,
            self.health_topic,
            make_health(
                self.node_id,
                backend="replay" if not self.inference_only else "inference",
                uptime_sec=time.monotonic() - self._started,
            ),
            qos=self.qos,
            retain=False,
        )

    def run(self) -> int:
        STOP.clear()
        self._started = time.monotonic()
        if not self.inference_only:
            self._load_training_state()
        self._connect()
        worker: threading.Thread | None = None
        if not self.inference_only:
            worker = threading.Thread(
                target=self._worker_loop, name=f"{self.node_id}-worker", daemon=True
            )
            worker.start()
        deadline = time.monotonic() + self.run_seconds if self.run_seconds else None
        try:
            last_heartbeat = 0.0
            while not STOP.is_set():
                self._drain_inbox()
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    break
                if now - last_heartbeat >= self.heartbeat_sec:
                    self._publish_heartbeat()
                    last_heartbeat = now
                STOP.wait(min(0.1, self.heartbeat_sec))
        finally:
            STOP.set()
            if self.client is not None and self.client.is_connected():
                info = publish_json(
                    self.client,
                    self.status_topic,
                    make_status(self.node_id, "offline", "graceful"),
                    qos=self.qos,
                    retain=True,
                )
                end = time.monotonic() + 2.0
                while not info.is_published() and time.monotonic() < end:
                    time.sleep(0.05)
            if self.client is not None:
                self.client.disconnect()
                self.client.loop_stop()
            if worker is not None:
                worker.join(timeout=2.0)
            LOGGER.info("%s stopped", self.node_id)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 4 long-lived federated node")
    parser.add_argument("--config", default=None)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--inference-only", action="store_true")
    parser.add_argument("--dummy", action="store_true")
    parser.add_argument("--dummy-value", type=float, default=1.0)
    parser.add_argument("--dummy-samples", type=int, default=100)
    parser.add_argument("--dummy-count", type=int, default=9025)
    parser.add_argument("--upload-delay", type=float, default=0.0)
    parser.add_argument("--ack-timeout", type=float, default=30.0)
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--run-seconds", type=float, default=None)
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def _main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.verbose == 0 else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def stop_handler(signum: int, frame: Any) -> None:
        del signum, frame
        STOP.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    raise SystemExit(
        FederatedNode(
            args.config,
            node_id=args.node_id,
            host=args.host,
            port=args.port,
            seed=args.seed,
            window_hours=args.window_hours,
            inference_only=args.inference_only,
            dummy=args.dummy,
            dummy_value=args.dummy_value,
            dummy_samples=args.dummy_samples,
            dummy_count=args.dummy_count,
            upload_delay=args.upload_delay,
            ack_timeout=args.ack_timeout,
            keepalive=args.keepalive,
            run_seconds=args.run_seconds,
        ).run()
    )


if __name__ == "__main__":
    _main()
