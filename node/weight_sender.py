"""Stage 3 weight sender: publish one model update or the global model.

Examples:
    # Real improved 24 h Keras weights, round update, wait for the server ack
    python -m node.weight_sender --node-id node1 --round 1 --wait-ack --verbose

    # Dummy array plumbing test (no TensorFlow)
    python -m node.weight_sender --node-id node1 --round 1 --dummy --wait-ack

Only weights, checksums, and prediction fingerprints are published.  Raw
PM2.5/temperature/humidity readings never enter this process.
"""

from __future__ import annotations

import argparse
import base64
import logging
import signal
import threading
import uuid
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
from common.mqtt_utils import create_client, loads, publish_json, reason_code_value
from common.weight_transfer import (
    DEFAULT_CHUNK_SIZE,
    build_chunk_message,
    build_transfer_metadata,
    encode_weights,
    global_announce_topic,
    global_chunk_topic,
    make_dummy_weights,
    prediction_digest,
    prediction_probe,
    prediction_sample,
    round_ack_topic,
    round_update_chunk_topic,
    round_update_meta_topic,
    split_weight_payload,
    validate_header,
)

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


def _wait_publish(info: mqtt.MQTTMessageInfo, what: str, timeout: float = 10.0) -> None:
    info.wait_for_publish(timeout=timeout)
    if not info.is_published():
        raise TimeoutError(f"{what} publish was not confirmed within {timeout}s")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 3 chunked weight sender")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mode", choices=["update", "global"], default="update")
    parser.add_argument("--node-id", default="node1")
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--model-version", default=None)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--dummy", action="store_true", help="send a dummy array")
    parser.add_argument("--dummy-count", type=int, default=9025)
    parser.add_argument(
        "--train-epochs",
        type=int,
        default=0,
        help="train the improved model on the node's real data before sending",
    )
    parser.add_argument("--wait-ack", action="store_true")
    parser.add_argument("--ack-timeout", type=float, default=10.0)
    parser.add_argument(
        "--corrupt-chunk",
        type=int,
        default=None,
        help="test hook: corrupt this chunk after its SHA-256 is computed",
    )
    parser.add_argument(
        "--drop-chunk",
        type=int,
        default=None,
        help="test hook: do not publish this chunk",
    )
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def _build_real_weights(
    config: dict[str, Any],
    *,
    node_id: str,
    window_hours: int,
    seed: int,
    train_epochs: int,
) -> tuple[np.ndarray, dict[str, Any], Any]:
    from common.model import build_model_from_config, flatten_weights

    model_cfg = config.get("model", {})
    features = list(config.get("features", ["pm25", "temp", "rh"]))
    n_features = len(features) + 2
    model_config = {
        "architecture": "cnn_rnn_improved",
        "window_hours": window_hours,
        "n_features": n_features,
        "conv_filters": int(model_cfg.get("conv_filters", 64)),
        "kernel_size": int(model_cfg.get("kernel_size", 2)),
        "pool_size": 1,
        "rnn_units": int(model_cfg.get("rnn_units", 64)),
        "dropout": float(model_cfg.get("dropout", 0.2)),
        "learning_rate": float(model_cfg.get("learning_rate", 0.001)),
        "seed": seed,
        "horizon": 1,
        "delta": True,
        "cyclic_hour": True,
        "trained_epochs": train_epochs,
    }
    model = build_model_from_config(model_config)
    if train_epochs > 0:
        if "scaler" not in config or "dataset_path" not in config:
            raise ValueError(
                "--train-epochs needs dataset_path and scaler in config.json"
            )
        from common.improved import prepare_improved_node
        from common.preprocess import load_raw

        raw = load_raw(resolve_path(config["dataset_path"]))
        if node_id not in config["nodes"]:
            raise ValueError(f"unknown node_id {node_id!r}")
        prepared = prepare_improved_node(
            raw,
            node_id=node_id,
            year=int(config["nodes"][node_id]),
            scaler=config["scaler"],
            features=features,
            window_hours=window_hours,
            horizon=1,
            delta=True,
            cyclic_hour=True,
            train_fraction=float(config["train_fraction"]),
            val_fraction_of_train=float(config["val_fraction_of_train"]),
        )
        model.fit(
            prepared["X_train"],
            prepared["y_train"],
            validation_data=(prepared["X_val"], prepared["y_val"]),
            epochs=train_epochs,
            batch_size=int(model_cfg.get("batch_size", 64)),
            shuffle=True,
            verbose=0,
        )
        print(
            f"trained {node_id} for {train_epochs} epoch(s) on "
            f"{len(prepared['X_train'])} windows",
            flush=True,
        )
    return flatten_weights(model), model_config, model


def run(
    config_path: str | Path | None = None,
    *,
    mode: str = "update",
    node_id: str = "node1",
    round_number: int = 1,
    host: str | None = None,
    port: int | None = None,
    chunk_size: int | None = None,
    model_version: str | None = None,
    window_hours: int = 24,
    seed: int | None = None,
    dummy: bool = False,
    dummy_count: int = 9025,
    train_epochs: int = 0,
    wait_ack: bool = False,
    ack_timeout: float = 10.0,
    corrupt_chunk: int | None = None,
    drop_chunk: int | None = None,
    keepalive: int = 30,
) -> int:
    """Publish one announce/update plus all chunks; optionally wait for an ack."""
    STOP.clear()
    config = load_config(config_path)
    mqtt_cfg = config.get("mqtt", {})
    broker_host = str(host or mqtt_cfg.get("host", "127.0.0.1"))
    broker_port = int(port or mqtt_cfg.get("port", 1883))
    qos = int(mqtt_cfg.get("qos", 1))
    chunk_bytes = int(chunk_size or mqtt_cfg.get("chunk_size", DEFAULT_CHUNK_SIZE))
    run_seed = int(seed if seed is not None else config.get("seed", 42))
    base_topic = str(mqtt_cfg.get("base_topic", "aq"))

    if mode == "update":
        if node_id not in config.get("nodes", {}):
            raise ValueError(f"unknown node_id {node_id!r}")
        if node_id in inference_only_node_ids(config):
            raise ValueError(
                f"node_id {node_id!r} is inference-only and must not upload weights"
            )
        if node_id not in training_node_ids(config):
            raise ValueError(
                f"node_id {node_id!r} is not in federated.training_nodes"
            )
        publisher_id = node_id
        if round_number < 1:
            raise ValueError("--round must be positive")
    else:
        if node_id != "flserver":
            LOGGER.warning(
                "global mode is published by the laptop server; using node_id=flserver"
            )
        node_id = "flserver"
        publisher_id = "flserver"

    if dummy:
        weights = make_dummy_weights(dummy_count, run_seed)
        model_config: dict[str, Any] = {}
        kind = "dummy"
        version = model_version or "dummy-v1"
        prediction_sha = None
        prediction_values = None
        probe_seed = run_seed
    else:
        weights, model_config, model = _build_real_weights(
            config,
            node_id=node_id,
            window_hours=window_hours,
            seed=run_seed,
            train_epochs=train_epochs,
        )
        kind = "model"
        version = model_version or f"improved_w{window_hours}_seed{run_seed}"
        probe_seed = run_seed
        probe = prediction_probe(
            window_hours, int(model_config["n_features"]), seed=probe_seed
        )
        predictions = model.predict(probe, verbose=0)
        prediction_sha = prediction_digest(predictions)
        prediction_values = prediction_sample(predictions)

    metadata = build_transfer_metadata(
        weights,
        node_id=publisher_id,
        model_version=version,
        model_config=model_config,
        kind=kind,
        round_number=round_number if mode == "update" else None,
        chunk_size=chunk_bytes,
        probe_seed=probe_seed,
        prediction_sha256=prediction_sha,
        prediction_sample=prediction_values,
    )
    payload = encode_weights(weights)
    chunks = split_weight_payload(payload, chunk_bytes)

    if mode == "update":
        metadata_topic = round_update_meta_topic(base_topic, round_number, node_id)
        chunk_topic = lambda index: round_update_chunk_topic(
            base_topic, round_number, node_id, index
        )
        ack_topic = round_ack_topic(base_topic, round_number, node_id)
        retain_metadata = False
    else:
        metadata_topic = global_announce_topic(base_topic)
        chunk_topic = lambda index: global_chunk_topic(base_topic, index)
        ack_topic = None
        retain_metadata = True

    ack_event = threading.Event()
    ack_subscribed = threading.Event()
    ack_status: str | None = None
    ack_reason: str | None = None
    ack_missing: list[int] = []
    ack_predictions: bool | None = None
    connect_event = threading.Event()
    connected = False

    client = create_client(
        f"ws-{node_id}-{uuid.uuid4().hex[:6]}",
        broker_host,
        broker_port,
        keepalive=keepalive,
    )

    def on_connect(
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        nonlocal connected
        del userdata, flags, properties
        code = reason_code_value(reason_code)
        if code != 0:
            LOGGER.error("connect failed: %s", reason_code)
            connect_event.set()
            return
        connected = True
        LOGGER.info("connected to %s:%s as %s", broker_host, broker_port, node_id)
        if wait_ack and ack_topic is not None:
            client.subscribe(ack_topic, qos=qos)
        connect_event.set()

    def on_subscribe(
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_codes: Any,
        properties: Any = None,
    ) -> None:
        del client, userdata, mid, reason_codes, properties
        ack_subscribed.set()

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        nonlocal ack_status, ack_reason, ack_missing, ack_predictions
        del client, userdata
        LOGGER.debug("message on %s", message.topic)
        if ack_topic is None or message.topic != ack_topic:
            return
        try:
            ack = loads(message.payload)
            validate_header(ack)
            if ack.get("message_type") != "ack":
                raise ValueError("not an ack message")
            if ack.get("target_node") != node_id:
                raise ValueError("ack target_node mismatch")
            if ack.get("round") != round_number:
                raise ValueError("ack round mismatch")
            if ack.get("sha256") != metadata["sha256"]:
                raise ValueError("ack sha256 mismatch")
        except (ValueError, TypeError) as exc:
            LOGGER.warning("bad ack on %s: %s", message.topic, exc)
            return
        ack_status = str(ack.get("status"))
        ack_reason = ack.get("reason")
        ack_missing = list(ack.get("missing") or [])
        ack_predictions = ack.get("predictions_match")
        ack_event.set()

    def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        code = reason_code_value(reason_code) if reason_code is not None else None
        if code == 0:
            LOGGER.info("disconnected cleanly")
        else:
            LOGGER.warning("disconnected unexpectedly (%s); paho will reconnect", reason_code)

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    backoff = 1.0
    while not STOP.is_set():
        try:
            client.connect(broker_host, broker_port, keepalive)
            break
        except OSError as exc:
            LOGGER.warning(
                "broker unavailable at %s:%s (%s); retry in %.1fs",
                broker_host,
                broker_port,
                exc,
                backoff,
            )
            STOP.wait(backoff)
            backoff = min(backoff * 2.0, 30.0)
    if STOP.is_set():
        return 1

    client.loop_start()
    try:
        if not connect_event.wait(timeout=10.0) or not connected:
            print("connect failed", flush=True)
            return 1
        if wait_ack and ack_topic is not None and not ack_subscribed.wait(
            timeout=5.0
        ):
            print("ack subscription was not confirmed", flush=True)
            return 1

        print(
            f"publishing mode={mode} node_id={publisher_id} "
            f"round={round_number if mode == 'update' else '-'} "
            f"model_version={version} kind={kind} "
            f"size={metadata['size']} chunks={len(chunks)} "
            f"chunk_size={chunk_bytes} sha256={metadata['sha256']}",
            flush=True,
        )
        _wait_publish(
            publish_json(
                client,
                metadata_topic,
                metadata,
                qos=qos,
                retain=retain_metadata,
            ),
            "metadata",
        )
        for index, chunk in enumerate(chunks):
            if STOP.is_set():
                return 1
            if drop_chunk == index:
                LOGGER.warning("test hook: dropping chunk %s", index)
                continue
            message = build_chunk_message(metadata, index, chunk)
            if corrupt_chunk == index:
                # Corrupt the bytes after the sender computed chunk_sha256 so
                # the receiver sees a real per-chunk SHA-256 mismatch.
                raw = bytearray(base64.b64decode(message["data"]))
                raw[0] ^= 0xFF
                message["data"] = base64.b64encode(bytes(raw)).decode("ascii")
                LOGGER.warning("test hook: corrupting chunk %s", index)
            _wait_publish(
                publish_json(
                    client, chunk_topic(index), message, qos=qos, retain=False
                ),
                f"chunk {index}",
            )
        print("all chunks published", flush=True)

        if not wait_ack:
            return 0
        if ack_topic is None:
            return 0
        if not ack_event.wait(timeout=ack_timeout):
            print(f"ack timeout after {ack_timeout:.1f}s", flush=True)
            return 2
        if ack_status == "accepted":
            print(
                f"ack accepted sha256={metadata['sha256']} "
                f"chunks_received={metadata['chunks']} "
                f"predictions_match={ack_predictions}",
                flush=True,
            )
            return 0
        print(
            f"ack rejected reason={ack_reason} missing={ack_missing}",
            flush=True,
        )
        return 2
    finally:
        client.disconnect()
        client.loop_stop()
        LOGGER.info("sender stopped")


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
        run(
            args.config,
            mode=args.mode,
            node_id=args.node_id,
            round_number=args.round,
            host=args.host,
            port=args.port,
            chunk_size=args.chunk_size,
            model_version=args.model_version,
            window_hours=args.window_hours,
            seed=args.seed,
            dummy=args.dummy,
            dummy_count=args.dummy_count,
            train_epochs=args.train_epochs,
            wait_ack=args.wait_ack,
            ack_timeout=args.ack_timeout,
            corrupt_chunk=args.corrupt_chunk,
            drop_chunk=args.drop_chunk,
            keepalive=args.keepalive,
        )
    )


if __name__ == "__main__":
    _main()
