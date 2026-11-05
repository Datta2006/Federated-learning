"""Stage 4 federated server: online nodes -> FedAvg -> registered model.

The round pipeline is a DAG::

    check_online_nodes -> select_clients -> broadcast_global_model
    -> wait_for_updates -> validate_updates -> fedavg_aggregate
    -> register_model -> announce

All broker I/O is queued from paho callbacks and processed by the round task,
so validation, aggregation, and registry writes never block the network loop.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import queue
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
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
from common.federated import (
    UpdateValidationError,
    fedavg,
    model_version_for_round,
    validate_update,
    validate_update_metadata,
    weighted_validation_loss,
)
from common.improved import improved_model_config
from common.model_delivery import GlobalModelPublisher
from common.mqtt_utils import (
    create_client,
    dumps,
    loads,
    make_message,
    publish_json,
    reason_code_value,
    utc_now_iso,
)
from common.weight_transfer import (
    TransferError,
    WeightReceiver,
    build_ack_message,
    decode_chunk_message,
    make_dummy_weights,
    parse_round_update_chunk_topic,
    parse_round_update_meta_topic,
    round_ack_topic,
    round_start_topic,
    round_update_chunk_filter,
    round_update_meta_filter,
)
from server.dag_runner import DAG, Task, run_dag

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()

ROUND_COLUMNS = [
    "round",
    "selected",
    "received",
    "dropped_nodes",
    "bytes_up",
    "bytes_down",
    "round_time_sec",
    "weighted_val_loss",
    "evaluated_version",
    "model_version",
]


class RoundError(RuntimeError):
    """Raised when a round cannot continue."""


@dataclass
class AcceptedUpdate:
    node_id: str
    metadata: dict[str, Any]
    weights: np.ndarray
    n_samples: int
    n_val: int
    val_loss: float


@dataclass
class ActiveUpdate:
    node_id: str
    metadata: dict[str, Any]
    receiver: WeightReceiver
    last_activity: float


@dataclass
class RoundOutcome:
    round_number: int
    selected: list[str] = field(default_factory=list)
    received: int = 0
    dropped: list[str] = field(default_factory=list)
    bytes_up: int = 0
    bytes_down: int = 0
    seconds: float = 0.0
    weighted_val_loss: float | None = None
    evaluated_version: str = ""
    model_version: str = ""


class RoundCollector:
    """Collect and validate one round's updates; acks are published immediately."""

    def __init__(
        self,
        *,
        base_topic: str,
        round_number: int,
        model_version: str,
        selected: list[str],
        deadline: float,
        training_nodes: set[str],
        inference_only_nodes: set[str],
        reference_weights: np.ndarray | None,
        ack_callback: Callable[[dict[str, Any], str, str | None, list[int]], int],
    ) -> None:
        self.base_topic = base_topic
        self.round_number = round_number
        self.model_version = model_version
        self.selected = set(selected)
        self.deadline = deadline
        self.training_nodes = set(training_nodes)
        self.inference_only_nodes = set(inference_only_nodes)
        self.reference_weights = (
            None
            if reference_weights is None
            else np.asarray(reference_weights, dtype=np.float32)
        )
        self.ack_callback = ack_callback
        self.active: dict[str, ActiveUpdate] = {}
        self.accepted: dict[str, AcceptedUpdate] = {}
        self.rejected: dict[str, str] = {}
        self.bytes_up = 0
        self.bytes_down = 0

    @property
    def all_reported(self) -> bool:
        return all(
            node in self.accepted or node in self.rejected for node in self.selected
        )

    @property
    def received(self) -> int:
        return len(self.accepted)

    @property
    def dropped_nodes(self) -> list[str]:
        return sorted(self.selected.difference(self.accepted))

    @property
    def weighted_val_loss(self) -> float | None:
        if not self.accepted:
            return None
        return weighted_validation_loss(
            [(update.val_loss, update.n_val) for update in self.accepted.values()]
        )

    def _ack(
        self,
        metadata: dict[str, Any],
        status: str,
        reason: str | None = None,
        missing: list[int] | None = None,
    ) -> None:
        self.bytes_down += self.ack_callback(metadata, status, reason, list(missing or []))

    def handle_metadata(self, topic: str, payload: bytes) -> None:
        parsed = parse_round_update_meta_topic(topic, self.base_topic)
        if parsed is None:
            return
        round_number, node_id = parsed
        if round_number != self.round_number:
            return
        self.bytes_up += len(payload)
        try:
            metadata = loads(payload)
        except (TypeError, ValueError) as exc:
            LOGGER.warning("bad update metadata on %s: %s", topic, exc)
            return

        if metadata.get("node_id") != node_id:
            self.rejected[node_id] = "metadata node_id disagrees with the topic"
            self._ack(metadata, "rejected", self.rejected[node_id])
            return
        if node_id in self.inference_only_nodes:
            self.rejected[node_id] = "node is inference-only and must not upload weights"
            self._ack(metadata, "rejected", self.rejected[node_id])
            return
        if node_id not in self.training_nodes:
            self.rejected[node_id] = "node is not a training node"
            self._ack(metadata, "rejected", self.rejected[node_id])
            return
        if node_id not in self.selected:
            self.rejected[node_id] = "node was not selected for this round"
            self._ack(metadata, "rejected", self.rejected[node_id])
            return
        try:
            validate_update_metadata(
                metadata,
                expected_round=self.round_number,
                expected_model_version=self.model_version,
                training_nodes=self.training_nodes,
                inference_only_nodes=self.inference_only_nodes,
            )
        except UpdateValidationError as exc:
            self.rejected[node_id] = str(exc)
            self._ack(metadata, "rejected", str(exc))
            return

        existing = self.active.get(node_id)
        if existing is not None and existing.metadata["sha256"] == metadata["sha256"]:
            existing.last_activity = time.monotonic()
            return
        self.active[node_id] = ActiveUpdate(
            node_id=node_id,
            metadata=metadata,
            receiver=WeightReceiver(metadata),
            last_activity=time.monotonic(),
        )

    def handle_chunk(self, topic: str, payload: bytes) -> None:
        parsed = parse_round_update_chunk_topic(topic, self.base_topic)
        if parsed is None:
            return
        round_number, node_id, _index = parsed
        if round_number != self.round_number:
            return
        self.bytes_up += len(payload)
        active = self.active.get(node_id)
        if active is None:
            LOGGER.warning("chunk without metadata for round=%s node=%s", round_number, node_id)
            return
        try:
            message = loads(payload)
            index, total_chunks, chunk = decode_chunk_message(
                message, expected_node_id=node_id
            )
            if message.get("model_version") != self.model_version:
                raise TransferError("chunk model_version disagrees with the round")
            active.receiver.accept_chunk(
                index,
                chunk,
                chunk_sha256=message["chunk_sha256"],
                topic_index=_index,
                total_chunks=total_chunks,
            )
        except (TypeError, ValueError, TransferError) as exc:
            self._reject_active(active, str(exc))
            return
        active.last_activity = time.monotonic()
        if active.receiver.complete:
            self._finish(active)

    def _reject_active(self, active: ActiveUpdate, reason: str) -> None:
        self.active.pop(active.node_id, None)
        self.rejected[active.node_id] = reason
        self._ack(active.metadata, "rejected", reason, active.receiver.missing_indices)

    def _finish(self, active: ActiveUpdate) -> None:
        try:
            payload = active.receiver.finalize()
            weights = validate_update(
                active.metadata,
                payload,
                expected_round=self.round_number,
                expected_model_version=self.model_version,
                training_nodes=self.training_nodes,
                inference_only_nodes=self.inference_only_nodes,
                reference_weights=self.reference_weights,
            )
        except (TransferError, UpdateValidationError, ValueError) as exc:
            self._reject_active(active, str(exc))
            return

        update = AcceptedUpdate(
            node_id=active.node_id,
            metadata=active.metadata,
            weights=weights,
            n_samples=int(active.metadata["n_samples"]),
            n_val=int(active.metadata["n_val"]),
            val_loss=float(active.metadata["val_loss"]),
        )
        self.accepted[active.node_id] = update
        self.active.pop(active.node_id, None)
        self._ack(active.metadata, "accepted")

    def expire(self, now: float) -> None:
        if now < self.deadline:
            return
        for active in list(self.active.values()):
            self._reject_active(
                active,
                f"missing chunks: {active.receiver.missing_indices}",
            )


class FederatedServer:
    """Long-lived MQTT coordinator for the Stage 4 round DAG."""

    def __init__(
        self,
        config_path: str | Path | None = None,
        *,
        host: str | None = None,
        port: int | None = None,
        rounds: int | None = None,
        local_epochs: int | None = None,
        learning_rate: float | None = None,
        seed: int | None = None,
        model_dir: str | Path | None = None,
        rounds_csv: str | Path | None = None,
        deadline_sec: float | None = None,
        min_clients: int | None = None,
        max_clients: int | None = None,
        startup_wait_sec: float = 0.0,
        client_wait_sec: float = 30.0,
        status_timeout_sec: float | None = None,
        window_hours: int = 24,
        dummy: bool = False,
        dummy_count: int = 9025,
        keepalive: int = 30,
        run_seconds: float | None = None,
    ) -> None:
        self.config = load_config(config_path)
        mqtt_cfg = self.config.get("mqtt", {})
        federated = self.config.get("federated", {})
        self.host = str(host or mqtt_cfg.get("host", "127.0.0.1"))
        self.port = int(port or mqtt_cfg.get("port", 1883))
        self.qos = int(mqtt_cfg.get("qos", 1))
        self.base_topic = str(mqtt_cfg.get("base_topic", "aq"))
        self.chunk_size = int(mqtt_cfg.get("chunk_size", 16384))
        self.keepalive = int(keepalive)
        self.rounds = int(rounds if rounds is not None else federated.get("rounds", 5))
        self.local_epochs = int(
            local_epochs
            if local_epochs is not None
            else federated.get("local_epochs", 1)
        )
        self.learning_rate = float(
            learning_rate
            if learning_rate is not None
            else self.config.get("model", {}).get("learning_rate", 0.001)
        )
        self.seed = int(seed if seed is not None else self.config.get("seed", 42))
        self.deadline_sec = float(
            deadline_sec
            if deadline_sec is not None
            else federated.get("deadline_sec", 120)
        )
        self.min_clients = int(
            min_clients
            if min_clients is not None
            else federated.get("min_clients", 3)
        )
        self.max_clients = max_clients
        self.startup_wait_sec = float(startup_wait_sec)
        self.client_wait_sec = float(client_wait_sec)
        heartbeat = float(mqtt_cfg.get("heartbeat_sec", 10))
        self.status_timeout_sec = float(
            status_timeout_sec
            if status_timeout_sec is not None
            else max(3.0 * heartbeat, 15.0)
        )
        self.window_hours = int(window_hours)
        self.dummy = bool(dummy)
        self.dummy_count = int(dummy_count)
        self.run_seconds = run_seconds

        self.training_nodes = training_node_ids(self.config)
        self.inference_nodes = inference_only_node_ids(self.config)
        configured_model_dir = self.config.get("paths", {}).get(
            "model_dir", "server/model_registry"
        )
        self.model_dir = (
            resolve_path(model_dir)
            if model_dir is not None
            else resolve_path(configured_model_dir)
        )
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.rounds_csv = (
            Path(rounds_csv).expanduser().resolve()
            if rounds_csv is not None
            else self.model_dir / "rounds.csv"
        )

        self.client: mqtt.Client | None = None
        self._inbox: queue.Queue[tuple[str, bytes, bool]] = queue.Queue()
        self._online: dict[str, dict[str, Any]] = {}
        self._health_seen: dict[str, float] = {}
        self._collector: RoundCollector | None = None
        self._current_round: int | None = None
        self._first_round_number = 1
        self._round_bytes_down = 0
        self._connected = threading.Event()

        self.latest_version: str | None = None
        self.latest_weights: np.ndarray | None = None
        self.latest_model_config: dict[str, Any] = {}
        self.latest_record: dict[str, Any] = {}
        self.kind = "dummy" if self.dummy else "model"

    # ------------------------------------------------------------------ MQTT
    def _connect(self) -> None:
        self.client = create_client(
            "fl-coordinator", self.host, self.port, keepalive=self.keepalive
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
            raise RoundError("stopped before connecting")
        self.client.loop_start()
        if not self._connected.wait(timeout=10.0):
            raise RoundError("MQTT connection was not confirmed")

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        code = reason_code_value(reason_code)
        if code != 0:
            LOGGER.error("connect failed: %s", reason_code)
            return
        LOGGER.info("connected to %s:%s", self.host, self.port)
        client.subscribe(
            [
                (f"{self.base_topic}/+/status", self.qos),
                (f"{self.base_topic}/+/health", self.qos),
                (round_update_meta_filter(self.base_topic), self.qos),
                (round_update_chunk_filter(self.base_topic), self.qos),
            ]
        )
        self._connected.set()

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        del client, userdata
        self._inbox.put((message.topic, bytes(message.payload), bool(message.retain)))

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
                topic, payload, retain = self._inbox.get_nowait()
            except queue.Empty:
                return
            try:
                self._handle_inbox(topic, payload, retain)
            except Exception:  # pragma: no cover - keep the server alive
                LOGGER.exception("unexpected message failure on %s", topic)

    def _handle_inbox(self, topic: str, payload: bytes, retain: bool) -> None:
        prefix = f"{self.base_topic}/"
        if topic.startswith(prefix):
            remainder = topic[len(prefix) :]
            node_id, _, leaf = remainder.partition("/")
            if leaf == "status":
                self._handle_status(node_id, payload, retain)
                return
            if leaf == "health":
                self._handle_health(node_id)
                return
        if self._collector is not None:
            if topic.endswith("/meta"):
                self._collector.handle_metadata(topic, payload)
            elif "/chunk/" in topic:
                self._collector.handle_chunk(topic, payload)

    def _handle_status(self, node_id: str, payload: bytes, retain: bool) -> None:
        try:
            message = loads(payload)
        except (TypeError, ValueError) as exc:
            LOGGER.warning("bad status on %s: %s", node_id, exc)
            return
        state = message.get("state")
        if state not in {"online", "offline"}:
            return
        previous = self._online.get(node_id, {}).get("state")
        self._online[node_id] = {
            "state": state,
            "received_at": time.monotonic(),
            "ts": message.get("ts"),
            "reason": message.get("reason"),
        }
        if state != previous:
            retained = " retained" if retain else ""
            reason = message.get("reason")
            detail = f" reason={reason}" if reason else ""
            print(
                f"status {node_id}: {state}{retained}{detail} "
                f"at {message.get('ts')}",
                flush=True,
            )

    def _handle_health(self, node_id: str) -> None:
        self._health_seen[node_id] = time.monotonic()

    def online_training_nodes(self) -> set[str]:
        now = time.monotonic()
        online: set[str] = set()
        for node_id in self.training_nodes:
            status = self._online.get(node_id)
            if not status or status["state"] != "online":
                continue
            last_seen = max(
                float(status["received_at"]),
                self._health_seen.get(node_id, 0.0),
            )
            if now - last_seen <= self.status_timeout_sec:
                online.add(node_id)
        return online

    def _wait_for_online(self, required: int, timeout: float) -> set[str]:
        deadline = time.monotonic() + timeout
        while not STOP.is_set():
            self._drain_inbox()
            online = self.online_training_nodes()
            if len(online) >= required:
                return online
            if time.monotonic() >= deadline:
                return online
            STOP.wait(0.1)
        return self.online_training_nodes()

    # -------------------------------------------------------------- registry
    def _read_json(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")

    def _update_best_pointer(self, record: dict[str, Any]) -> None:
        """Keep ``best.json`` on the lowest finite validation loss seen."""
        loss = record.get("weighted_val_loss")
        if loss is None:
            return
        best = self._read_json(self.model_dir / "best.json")
        if best is None:
            best_loss = None
        else:
            best_loss = best.get("weighted_val_loss")
        if best_loss is None or float(loss) < float(best_loss):
            self._write_json(self.model_dir / "best.json", record)

    def _save_model(
        self,
        *,
        version: str,
        weights: np.ndarray,
        model_config: dict[str, Any],
        round_number: int,
        weighted_val_loss: float | None,
        n_val: int,
        n_samples: int,
        sources: list[str],
    ) -> dict[str, Any]:
        record = {
            "model_version": version,
            "kind": self.kind,
            "model": model_config,
            "round": int(round_number),
            "created_utc": utc_now_iso(),
            "weighted_val_loss": weighted_val_loss,
            "n_val": int(n_val),
            "n_samples": int(n_samples),
            "sources": list(sources),
            "parameters": int(np.asarray(weights).size),
        }
        np.save(self.model_dir / f"global_{version}.npy", weights, allow_pickle=False)
        self._write_json(self.model_dir / f"global_{version}.json", record)
        self._write_json(self.model_dir / "latest.json", record)
        self._update_best_pointer(record)
        return record

    def _update_scored_model(
        self, version: str, weighted_val_loss: float, n_val: int, round_number: int
    ) -> None:
        """Attach a round's validation score to the model the nodes evaluated.

        Nodes always evaluate the model they received (the version broadcast at
        the start of the round), not the version produced by that round's
        aggregation.  The newly aggregated version stays unscored until a later
        round evaluates it.
        """
        record_path = self.model_dir / f"global_{version}.json"
        record = self._read_json(record_path)
        if record is None:
            LOGGER.warning("cannot score unknown model version %s", version)
            return
        record["weighted_val_loss"] = float(weighted_val_loss)
        record["n_val"] = int(n_val)
        record["evaluated_round"] = int(round_number)
        record["evaluated_utc"] = utc_now_iso()
        self._write_json(record_path, record)
        if version == self.latest_version:
            self._write_json(self.model_dir / "latest.json", record)
            self.latest_record = record
        self._update_best_pointer(record)

    def _ensure_initial_model(self) -> None:
        latest = self._read_json(self.model_dir / "latest.json")
        if latest is not None:
            version = str(latest["model_version"])
            weights_path = self.model_dir / f"global_{version}.npy"
            if weights_path.exists():
                self.latest_version = version
                self.latest_weights = np.load(weights_path, allow_pickle=False)
                self.latest_model_config = dict(latest.get("model", {}))
                self.latest_record = latest
                self.kind = str(latest.get("kind", self.kind))
                print(
                    f"resuming model {version} from {weights_path}",
                    flush=True,
                )
                return

        if self.dummy:
            weights = make_dummy_weights(self.dummy_count, self.seed)
            model_config: dict[str, Any] = {}
        else:
            from common.model import build_model_from_config, flatten_weights

            model_config = improved_model_config(
                self.config, window_hours=self.window_hours, seed=self.seed
            )
            model = build_model_from_config(model_config)
            weights = flatten_weights(model)
        self.latest_version = model_version_for_round(0)
        self.latest_weights = weights
        self.latest_model_config = model_config
        self.latest_record = self._save_model(
            version=self.latest_version,
            weights=weights,
            model_config=model_config,
            round_number=0,
            weighted_val_loss=None,
            n_val=0,
            n_samples=0,
            sources=[],
        )
        print(
            f"initialized {self.latest_version} parameters={weights.size} "
            f"kind={self.kind}",
            flush=True,
        )

    # -------------------------------------------------------------- messages
    def _publish_current_model(self) -> int:
        if self.client is None or self.latest_weights is None or self.latest_version is None:
            raise RoundError("no model to publish")
        publisher = GlobalModelPublisher(
            self.client,
            self.base_topic,
            qos=self.qos,
            chunk_size=self.chunk_size,
            retain=True,
            wait=True,
        )
        published = publisher.publish(
            self.latest_weights,
            model_version=self.latest_version,
            model_config=self.latest_model_config,
            kind=self.kind,
            extra_fields={"federated_round": int(self.latest_record.get("round", 0))},
        )
        return published.bytes

    def _publish_round_start(
        self,
        round_number: int,
        selected: list[str],
        deadline_ts: float,
    ) -> int:
        if self.client is None or self.latest_version is None:
            raise RoundError("cannot start a round without a global model")
        message = make_message(
            "flserver",
            message_type="round_start",
            round=round_number,
            model_version=self.latest_version,
            local_epochs=self.local_epochs,
            learning_rate=self.learning_rate,
            deadline_ts=deadline_ts,
            selected_nodes=list(selected),
            min_clients=self.min_clients,
        )
        info = publish_json(
            self.client,
            round_start_topic(self.base_topic, round_number),
            message,
            qos=self.qos,
            retain=False,
        )
        info.wait_for_publish(timeout=10.0)
        return len(dumps(message).encode("utf-8"))

    def _publish_ack(
        self,
        metadata: dict[str, Any],
        status: str,
        reason: str | None,
        missing: list[int],
    ) -> int:
        if self.client is None:
            return 0
        try:
            round_number = int(metadata.get("round"))
            node_id = str(metadata["node_id"])
            chunks_received = (
                int(metadata.get("chunks", 0)) if status == "accepted" else 0
            )
            ack = build_ack_message(
                metadata,
                status=status,
                reason=reason,
                chunks_received=chunks_received,
                missing=missing,
            )
            info = publish_json(
                self.client,
                round_ack_topic(self.base_topic, round_number, node_id),
                ack,
                qos=self.qos,
                retain=False,
            )
            info.wait_for_publish(timeout=10.0)
            print(
                f"ack {status} round={round_number} node={node_id} "
                f"reason={reason}",
                flush=True,
            )
            return len(dumps(ack).encode("utf-8"))
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("could not publish ack: %s", exc)
            return 0

    # ----------------------------------------------------------------- round
    def _task_check_online(self, context: dict[str, Any]) -> dict[str, Any]:
        del context
        if self._current_round == self._first_round_number and self.startup_wait_sec > 0:
            self._wait_for_online(
                len(self.training_nodes), timeout=self.startup_wait_sec
            )
        online = self._wait_for_online(
            self.min_clients, timeout=self.client_wait_sec
        )
        if len(online) < self.min_clients:
            raise RoundError(
                f"only {len(online)} training node(s) online; "
                f"need {self.min_clients}"
            )
        print(f"online nodes: {' '.join(sorted(online))}", flush=True)
        return {"online_nodes": sorted(online)}

    def _task_select(self, context: dict[str, Any]) -> dict[str, Any]:
        online = list(context["online_nodes"])
        selected = online if self.max_clients is None else online[: self.max_clients]
        if len(selected) < self.min_clients:
            raise RoundError(
                f"selected {len(selected)} node(s); need {self.min_clients}"
            )
        print(f"selected clients: {' '.join(selected)}", flush=True)
        return {"selected_nodes": selected}

    def _task_broadcast(self, context: dict[str, Any]) -> dict[str, Any]:
        selected = list(context["selected_nodes"])
        if self._current_round is None or self.latest_version is None:
            raise RoundError("round state is incomplete")
        self._round_bytes_down += self._publish_current_model()
        deadline_monotonic = time.monotonic() + self.deadline_sec
        deadline_ts = time.time() + self.deadline_sec
        self._round_bytes_down += self._publish_round_start(
            self._current_round, selected, deadline_ts
        )
        self._collector = RoundCollector(
            base_topic=self.base_topic,
            round_number=self._current_round,
            model_version=self.latest_version,
            selected=selected,
            deadline=deadline_monotonic,
            training_nodes=self.training_nodes,
            inference_only_nodes=self.inference_nodes,
            reference_weights=(
                None
                if self.dummy or self.latest_weights is None
                else self.latest_weights
            ),
            ack_callback=self._publish_ack,
        )
        print(
            f"round {self._current_round} started model={self.latest_version} "
            f"deadline_ts={deadline_ts:.0f}",
            flush=True,
        )
        return {"deadline": deadline_monotonic}

    def _task_wait(self, context: dict[str, Any]) -> dict[str, Any]:
        collector = self._collector
        if collector is None:
            raise RoundError("no active round collector")
        deadline = float(context["deadline"])
        while not STOP.is_set():
            self._drain_inbox()
            now = time.monotonic()
            collector.expire(now)
            if collector.all_reported or now >= deadline:
                break
            STOP.wait(0.05)
        self._drain_inbox()
        collector.expire(time.monotonic())
        print(
            f"round {collector.round_number} collected "
            f"{len(collector.accepted)}/{len(collector.selected)}",
            flush=True,
        )
        return {
            "accepted_updates": list(collector.accepted.values()),
            "rejected_nodes": dict(collector.rejected),
        }

    def _task_validate(self, context: dict[str, Any]) -> dict[str, Any]:
        collector = self._collector
        if collector is None:
            raise RoundError("no active round collector")
        updates = list(context["accepted_updates"])
        if len(updates) < self.min_clients:
            raise RoundError(
                f"only {len(updates)} valid update(s); need {self.min_clients}"
            )
        loss = collector.weighted_val_loss
        print(
            f"validated {len(updates)} update(s) weighted_val_loss={loss} "
            f"evaluated={self.latest_version}",
            flush=True,
        )
        return {
            "weighted_val_loss": loss,
            "evaluated_version": self.latest_version or "",
            "evaluated_n_val": sum(update.n_val for update in updates),
        }

    def _task_aggregate(self, context: dict[str, Any]) -> dict[str, Any]:
        updates: list[AcceptedUpdate] = list(context["accepted_updates"])
        weights = fedavg(
            [update.weights for update in updates],
            [update.n_samples for update in updates],
        )
        total_samples = sum(update.n_samples for update in updates)
        print(
            f"fedavg {len(updates)} update(s) total_samples={total_samples}",
            flush=True,
        )
        return {
            "aggregated_weights": weights,
            "total_samples": total_samples,
            "sources": [update.node_id for update in updates],
        }

    def _task_register(self, context: dict[str, Any]) -> dict[str, Any]:
        if self._current_round is None:
            raise RoundError("round number is missing")
        evaluated_version = str(context.get("evaluated_version") or "")
        evaluated_loss = context.get("weighted_val_loss")
        if evaluated_version and evaluated_loss is not None:
            self._update_scored_model(
                evaluated_version,
                float(evaluated_loss),
                int(context.get("evaluated_n_val", 0)),
                self._current_round,
            )
        version = model_version_for_round(self._current_round)
        record = self._save_model(
            version=version,
            weights=np.asarray(context["aggregated_weights"], dtype=np.float32),
            model_config=self.latest_model_config,
            round_number=self._current_round,
            weighted_val_loss=None,
            n_val=0,
            n_samples=int(context["total_samples"]),
            sources=list(context["sources"]),
        )
        self.latest_version = version
        self.latest_weights = np.asarray(
            context["aggregated_weights"], dtype=np.float32
        )
        self.latest_record = record
        print(
            f"registered {version} at {self.model_dir} "
            f"(scored {evaluated_version} val_loss={evaluated_loss})",
            flush=True,
        )
        return {"model_version": version, "evaluated_version": evaluated_version}

    def _task_announce(self, context: dict[str, Any]) -> dict[str, Any]:
        self._round_bytes_down += self._publish_current_model()
        return {"announced": context.get("model_version", self.latest_version)}

    def _write_round_row(self, outcome: RoundOutcome) -> None:
        self.rounds_csv.parent.mkdir(parents=True, exist_ok=True)
        exists = self.rounds_csv.exists()
        with self.rounds_csv.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ROUND_COLUMNS)
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "round": outcome.round_number,
                    "selected": " ".join(outcome.selected),
                    "received": outcome.received,
                    "dropped_nodes": " ".join(outcome.dropped),
                    "bytes_up": outcome.bytes_up,
                    "bytes_down": outcome.bytes_down,
                    "round_time_sec": round(outcome.seconds, 3),
                    "weighted_val_loss": (
                        "" if outcome.weighted_val_loss is None else outcome.weighted_val_loss
                    ),
                    "evaluated_version": outcome.evaluated_version,
                    "model_version": outcome.model_version,
                }
            )

    def run_round(self, round_number: int) -> bool:
        self._current_round = round_number
        self._collector = None
        self._round_bytes_down = 0
        started = time.monotonic()
        tasks = [
            Task(
                "check_online_nodes",
                self._task_check_online,
                timeout=max(
                    120.0,
                    self.startup_wait_sec + self.client_wait_sec + 60.0,
                ),
            ),
            Task(
                "select_clients",
                self._task_select,
                depends_on=("check_online_nodes",),
                timeout=10.0,
            ),
            Task(
                "broadcast_global_model",
                self._task_broadcast,
                depends_on=("select_clients",),
                timeout=60.0,
            ),
            Task(
                "wait_for_updates",
                self._task_wait,
                depends_on=("broadcast_global_model",),
                timeout=self.deadline_sec + 30.0,
            ),
            Task(
                "validate_updates",
                self._task_validate,
                depends_on=("wait_for_updates",),
                timeout=30.0,
            ),
            Task(
                "fedavg_aggregate",
                self._task_aggregate,
                depends_on=("validate_updates",),
                timeout=60.0,
            ),
            Task(
                "register_model",
                self._task_register,
                depends_on=("fedavg_aggregate",),
                timeout=60.0,
            ),
            Task(
                "announce",
                self._task_announce,
                depends_on=("register_model",),
                timeout=60.0,
            ),
        ]
        result = run_dag(DAG(tasks), logger=LOGGER)
        collector = self._collector
        outcome = RoundOutcome(
            round_number=round_number,
            selected=list(result.context.get("selected_nodes", [])),
            received=len(collector.accepted) if collector else 0,
            dropped=collector.dropped_nodes if collector else [],
            bytes_up=collector.bytes_up if collector else 0,
            bytes_down=self._round_bytes_down
            + (collector.bytes_down if collector else 0),
            seconds=time.monotonic() - started,
            weighted_val_loss=collector.weighted_val_loss if collector else None,
            evaluated_version=str(
                result.context.get(
                    "evaluated_version",
                    collector.model_version if collector else "",
                )
            ),
            model_version=str(
                result.context.get("model_version", self.latest_version or "")
            ),
        )
        if not result.success:
            failed = [
                f"{name}: {task.error}"
                for name, task in result.tasks.items()
                if task.status == "failed"
            ]
            print(f"round {round_number} failed: {'; '.join(failed)}", flush=True)
            outcome.model_version = self.latest_version or ""
            if collector is not None:
                collector.expire(time.monotonic())
                outcome.received = len(collector.accepted)
                outcome.dropped = collector.dropped_nodes
                outcome.bytes_up = collector.bytes_up
                outcome.bytes_down = self._round_bytes_down + collector.bytes_down
                outcome.weighted_val_loss = collector.weighted_val_loss
                outcome.evaluated_version = collector.model_version
        self._write_round_row(outcome)
        loss_text = (
            "None"
            if outcome.weighted_val_loss is None
            else f"{outcome.weighted_val_loss:.6f}"
        )
        print(
            f"round={outcome.round_number} selected={len(outcome.selected)} "
            f"received={outcome.received} "
            f"dropped={' '.join(outcome.dropped) or '-'} "
            f"bytes_up={outcome.bytes_up} bytes_down={outcome.bytes_down} "
            f"time={outcome.seconds:.2f}s val_loss={loss_text} "
            f"evaluated={outcome.evaluated_version or '-'} "
            f"version={outcome.model_version}",
            flush=True,
        )
        return bool(result.success)

    def run(self) -> int:
        STOP.clear()
        self._connect()
        try:
            self._ensure_initial_model()
            # Republish the current model so a broker restart or a late node can
            # always reconstruct it from retained announce + retained chunks.
            self._round_bytes_down += self._publish_current_model()
            if self.startup_wait_sec > 0:
                self._wait_for_online(
                    len(self.training_nodes), timeout=self.startup_wait_sec
                )
            deadline = (
                time.monotonic() + self.run_seconds if self.run_seconds else None
            )
            start_round = int(self.latest_record.get("round", 0)) + 1
            self._first_round_number = start_round
            for round_number in range(start_round, start_round + self.rounds):
                if STOP.is_set():
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    break
                self.run_round(round_number)
        finally:
            if self.client is not None:
                self.client.disconnect()
                self.client.loop_stop()
            LOGGER.info("server stopped")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 4 FedAvg MQTT coordinator")
    parser.add_argument("--config", default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--local-epochs", type=int, default=None)
    parser.add_argument("--learning-rate", type=float, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--rounds-csv", default=None)
    parser.add_argument("--deadline-sec", type=float, default=None)
    parser.add_argument("--min-clients", type=int, default=None)
    parser.add_argument("--max-clients", type=int, default=None)
    parser.add_argument("--startup-wait-sec", type=float, default=0.0)
    parser.add_argument("--client-wait-sec", type=float, default=30.0)
    parser.add_argument("--status-timeout-sec", type=float, default=None)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--dummy", action="store_true")
    parser.add_argument("--dummy-count", type=int, default=9025)
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
        FederatedServer(
            args.config,
            host=args.host,
            port=args.port,
            rounds=args.rounds,
            local_epochs=args.local_epochs,
            learning_rate=args.learning_rate,
            seed=args.seed,
            model_dir=args.model_dir,
            rounds_csv=args.rounds_csv,
            deadline_sec=args.deadline_sec,
            min_clients=args.min_clients,
            max_clients=args.max_clients,
            startup_wait_sec=args.startup_wait_sec,
            client_wait_sec=args.client_wait_sec,
            status_timeout_sec=args.status_timeout_sec,
            window_hours=args.window_hours,
            dummy=args.dummy,
            dummy_count=args.dummy_count,
            keepalive=args.keepalive,
            run_seconds=args.run_seconds,
        ).run()
    )


if __name__ == "__main__":
    _main()
