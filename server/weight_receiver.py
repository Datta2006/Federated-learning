"""Stage 3 weight receiver: reassemble, verify, save, and ack node updates.

Examples:
    # Receive round updates from all training nodes
    python -m server.weight_receiver --mode update --verbose

    # Receive the retained global model announce and its chunks
    python -m server.weight_receiver --mode global --verbose

The receiver rejects duplicate conflicts, bad per-chunk SHA-256, missing
chunks, whole-payload SHA-256 mismatches, and prediction mismatches.  Accepted
weights are saved as .npy plus a JSON receipt under the model registry.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import signal
import threading
import time
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
from common.mqtt_utils import (
    create_client,
    loads,
    publish_json,
    reason_code_value,
    utc_now_iso,
)
from common.weight_transfer import (
    TransferError,
    WeightReceiver,
    build_ack_message,
    decode_chunk_message,
    decode_weights,
    global_announce_topic,
    global_chunk_filter,
    parse_global_chunk_topic,
    parse_round_update_chunk_topic,
    parse_round_update_meta_topic,
    prediction_digest,
    prediction_probe,
    prediction_sample,
    round_ack_topic,
    round_update_chunk_filter,
    round_update_meta_filter,
    validate_transfer_metadata,
)

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


class ActiveTransfer:
    """One in-flight metadata + chunk stream."""

    def __init__(self, key: tuple[Any, ...], metadata: dict[str, Any]) -> None:
        self.key = key
        self.metadata = metadata
        self.receiver = WeightReceiver(metadata)
        self.last_activity = time.monotonic()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 3 chunked weight receiver")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mode", choices=["update", "global"], default="update")
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--missing-timeout", type=float, default=3.0)
    parser.add_argument("--run-seconds", type=float, default=None)
    parser.add_argument("--keepalive", type=int, default=30)
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "transfer"


def _verify_predictions(
    metadata: dict[str, Any], weights: np.ndarray
) -> bool | None:
    """Rebuild the model and check its probe predictions against metadata."""
    if metadata.get("kind") != "model":
        return None
    expected = metadata.get("prediction_sample")
    expected_digest = metadata.get("prediction_sha256")
    if expected is None and expected_digest is None:
        return None
    from common.model import build_model_from_config, unflatten_weights

    model_cfg = metadata["model"]
    model = build_model_from_config(model_cfg)
    unflatten_weights(model, weights)
    probe = prediction_probe(
        int(model_cfg["window_hours"]),
        int(model_cfg["n_features"]),
        seed=int(metadata.get("probe_seed", 42)),
    )
    predictions = model.predict(probe, verbose=0)
    digest_match = (
        expected_digest is None or expected_digest == prediction_digest(predictions)
    )
    if expected is None:
        print(
            f"prediction check sample_match=None digest_match={digest_match}",
            flush=True,
        )
        return bool(digest_match)
    actual = np.asarray(prediction_sample(predictions), dtype=np.float32)
    expected_array = np.asarray(expected, dtype=np.float32)
    sample_match = bool(np.allclose(actual, expected_array, rtol=1e-5, atol=1e-6))
    print(
        f"prediction check sample_match={sample_match} "
        f"digest_match={digest_match}",
        flush=True,
    )
    return bool(sample_match and digest_match)


def _save_transfer(
    active: ActiveTransfer, weights: np.ndarray, out_dir: Path, predictions_match
) -> Path:
    metadata = active.metadata
    if active.key[0] == "global":
        stem = f"global_{_safe_stem(metadata['model_version'])}"
    else:
        round_number, node_id = active.key
        stem = f"round_{round_number}_{_safe_stem(node_id)}"
    weights_path = out_dir / f"{stem}.npy"
    np.save(weights_path, weights, allow_pickle=False)
    receipt = {
        "metadata": metadata,
        "received_chunks": active.receiver.received_chunks,
        "duplicates_ignored": active.receiver.duplicates_ignored,
        "predictions_match": predictions_match,
        "saved_utc": utc_now_iso(),
    }
    with (out_dir / f"{stem}.json").open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return weights_path


def run(
    config_path: str | Path | None = None,
    *,
    mode: str = "update",
    round_filter: int | None = None,
    host: str | None = None,
    port: int | None = None,
    out_dir: str | Path | None = None,
    missing_timeout: float = 3.0,
    run_seconds: float | None = None,
    keepalive: int = 30,
) -> int:
    """Subscribe, receive transfers, verify them, and publish update acks."""
    STOP.clear()
    config = load_config(config_path)
    mqtt_cfg = config.get("mqtt", {})
    broker_host = str(host or mqtt_cfg.get("host", "127.0.0.1"))
    broker_port = int(port or mqtt_cfg.get("port", 1883))
    qos = int(mqtt_cfg.get("qos", 1))
    base_topic = str(mqtt_cfg.get("base_topic", "aq"))
    if missing_timeout <= 0:
        raise ValueError("--missing-timeout must be positive")
    if round_filter is not None and round_filter < 1:
        raise ValueError("--round must be positive")

    if out_dir is None:
        configured = config.get("paths", {}).get("model_dir", "server/model_registry")
        registry = resolve_path(configured)
    else:
        registry = Path(out_dir).expanduser().resolve()
    registry.mkdir(parents=True, exist_ok=True)

    allowed_nodes = training_node_ids(config)
    inference_nodes = inference_only_node_ids(config)
    active: dict[tuple[Any, ...], ActiveTransfer] = {}

    if mode == "global":
        topics = [global_announce_topic(base_topic), global_chunk_filter(base_topic)]
    else:
        topics = [
            round_update_meta_filter(base_topic),
            round_update_chunk_filter(base_topic),
        ]

    client = create_client(
        f"wr-{uuid.uuid4().hex[:8]}", broker_host, broker_port, keepalive=keepalive
    )
    connected = False

    def publish_ack(
        transfer: ActiveTransfer,
        *,
        status: str,
        reason: str | None = None,
        missing: list[int] | None = None,
        predictions_match: bool | None = None,
    ) -> None:
        round_number = transfer.metadata.get("round")
        if round_number is None:
            return
        ack = build_ack_message(
            transfer.metadata,
            status=status,
            reason=reason,
            chunks_received=transfer.receiver.received_chunks,
            missing=missing,
            predictions_match=predictions_match,
        )
        topic = round_ack_topic(base_topic, int(round_number), transfer.metadata["node_id"])
        # Do not call wait_for_publish() here: this runs inside paho's network
        # callback, and blocking it would prevent the client from processing
        # its own PUBACK. QoS 1 keeps the ack queued until the broker confirms.
        publish_json(client, topic, ack, qos=qos, retain=False)
        print(
            f"ack {status} round={round_number} node={transfer.metadata['node_id']} "
            f"reason={reason}",
            flush=True,
        )

    def reject(
        transfer: ActiveTransfer,
        reason: str,
        *,
        missing: list[int] | None = None,
    ) -> None:
        missing_values = list(missing or transfer.receiver.missing_indices)
        print(
            f"rejected round={transfer.metadata.get('round')} "
            f"node={transfer.metadata['node_id']} reason={reason} "
            f"missing={missing_values}",
            flush=True,
        )
        # Drop the transfer before publishing so a publish failure cannot leave
        # a complete-but-unacked transfer stuck in the active map.
        active.pop(transfer.key, None)
        publish_ack(
            transfer, status="rejected", reason=reason, missing=missing_values
        )

    def finish(transfer: ActiveTransfer) -> None:
        try:
            payload = transfer.receiver.finalize()
            weights = decode_weights(
                payload,
                transfer.metadata["dtype"],
                transfer.metadata["count"],
            )
            predictions_match = _verify_predictions(transfer.metadata, weights)
            if predictions_match is False:
                reject(transfer, "prediction mismatch")
                return
            saved = _save_transfer(transfer, weights, registry, predictions_match)
        except (TransferError, ValueError) as exc:
            reject(transfer, str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("receiver failure for transfer %s", transfer.key)
            reject(transfer, f"receiver error: {exc}")
            return

        print(
            f"accepted round={transfer.metadata.get('round')} "
            f"node={transfer.metadata['node_id']} "
            f"model_version={transfer.metadata['model_version']} "
            f"size={transfer.metadata['size']} chunks={transfer.metadata['chunks']} "
            f"sha256={transfer.metadata['sha256']} "
            f"predictions_match={predictions_match} saved={saved}",
            flush=True,
        )
        active.pop(transfer.key, None)
        publish_ack(
            transfer,
            status="accepted",
            predictions_match=predictions_match,
        )

    def handle_metadata(topic: str, payload: Any) -> None:
        if mode == "global":
            if topic != global_announce_topic(base_topic):
                return
            metadata = loads(payload)
            validate_transfer_metadata(metadata)
            if metadata.get("message_type") != "announce":
                raise TransferError("global announce has the wrong message_type")
            if metadata.get("node_id") != "flserver":
                raise TransferError("global announce must be published by flserver")
            key: tuple[Any, ...] = ("global",)
        else:
            parsed = parse_round_update_meta_topic(topic, base_topic)
            if parsed is None:
                return
            round_number, node_id = parsed
            if round_filter is not None and round_number != round_filter:
                return
            metadata = loads(payload)
            validate_transfer_metadata(metadata)
            if metadata.get("message_type") != "update_meta":
                raise TransferError("round update has the wrong message_type")
            if metadata.get("node_id") != node_id:
                raise TransferError("metadata node_id disagrees with the topic")
            if metadata.get("round") != round_number:
                raise TransferError("metadata round disagrees with the topic")
            if node_id not in allowed_nodes:
                reason = (
                    "node is inference-only and must not upload weights"
                    if node_id in inference_nodes
                    else "node is not a training node"
                )
                ack = build_ack_message(
                    metadata,
                    status="rejected",
                    reason=reason,
                    chunks_received=0,
                    missing=[],
                )
                publish_json(
                    client,
                    round_ack_topic(base_topic, round_number, node_id),
                    ack,
                    qos=qos,
                    retain=False,
                )
                print(
                    f"rejected round={round_number} node={node_id} "
                    f"reason={reason} missing=[]",
                    flush=True,
                )
                return
            key = (round_number, node_id)

        existing = active.get(key)
        if existing is not None:
            if existing.metadata["sha256"] == metadata["sha256"]:
                existing.last_activity = time.monotonic()
                LOGGER.info("duplicate metadata for %s ignored", key)
                return
            LOGGER.warning("replacing incomplete transfer for %s", key)
        transfer = ActiveTransfer(key, metadata)
        active[key] = transfer
        print(
            f"metadata round={metadata.get('round')} node={metadata['node_id']} "
            f"model_version={metadata['model_version']} size={metadata['size']} "
            f"chunks={metadata['chunks']} sha256={metadata['sha256']}",
            flush=True,
        )

    def handle_chunk(topic: str, payload: Any) -> None:
        if mode == "global":
            index = parse_global_chunk_topic(topic, base_topic)
            if index is None:
                return
            key: tuple[Any, ...] = ("global",)
        else:
            parsed = parse_round_update_chunk_topic(topic, base_topic)
            if parsed is None:
                return
            round_number, node_id, index = parsed
            if round_filter is not None and round_number != round_filter:
                return
            key = (round_number, node_id)

        transfer = active.get(key)
        if transfer is None:
            LOGGER.warning("chunk without metadata on %s", topic)
            return
        try:
            message = loads(payload)
            chunk_index, total_chunks, chunk = decode_chunk_message(
                message, expected_node_id=transfer.metadata["node_id"]
            )
            if message.get("model_version") != transfer.metadata["model_version"]:
                raise TransferError("chunk model_version disagrees with metadata")
            if "round" in transfer.metadata and (
                message.get("round") != transfer.metadata["round"]
            ):
                raise TransferError("chunk round disagrees with metadata")
            result = transfer.receiver.accept_chunk(
                chunk_index,
                chunk,
                chunk_sha256=message["chunk_sha256"],
                topic_index=index,
                total_chunks=total_chunks,
            )
        except (TransferError, ValueError, TypeError) as exc:
            reject(transfer, str(exc))
            return

        transfer.last_activity = time.monotonic()
        if result == "duplicate":
            print(
                f"duplicate chunk {chunk_index} round={transfer.metadata.get('round')} "
                f"node={transfer.metadata['node_id']} ignored",
                flush=True,
            )
        if transfer.receiver.complete:
            finish(transfer)

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
            return
        connected = True
        LOGGER.info("connected to %s:%s", broker_host, broker_port)
        client.subscribe([(topic, qos) for topic in topics])
        print(f"subscribed {', '.join(topics)}", flush=True)

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        del client, userdata
        try:
            if message.topic.endswith("/meta") or (
                mode == "global" and message.topic == global_announce_topic(base_topic)
            ):
                handle_metadata(message.topic, message.payload)
            else:
                handle_chunk(message.topic, message.payload)
        except (TransferError, ValueError, TypeError) as exc:
            LOGGER.warning("bad message on %s: %s", message.topic, exc)
        except Exception:  # pragma: no cover - keep the subscriber alive
            LOGGER.exception("unexpected message failure on %s", message.topic)

    def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        code = reason_code_value(reason_code) if reason_code is not None else None
        if code == 0:
            LOGGER.info("disconnected cleanly")
        else:
            LOGGER.warning("disconnected unexpectedly (%s); paho will reconnect", reason_code)

    client.on_connect = on_connect
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
    deadline = time.monotonic() + run_seconds if run_seconds else None
    try:
        while not STOP.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                break
            now = time.monotonic()
            for transfer in list(active.values()):
                if transfer.receiver.complete:
                    continue
                if now - transfer.last_activity >= missing_timeout:
                    missing = transfer.receiver.missing_indices
                    reject(
                        transfer,
                        f"missing chunks: {missing}",
                        missing=missing,
                    )
            STOP.wait(0.05)
    except KeyboardInterrupt:
        LOGGER.info("interrupted")
    finally:
        client.disconnect()
        client.loop_stop()
        LOGGER.info("receiver stopped; active transfers: %s", list(active))
    return 0


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
            round_filter=args.round,
            host=args.host,
            port=args.port,
            out_dir=args.out_dir,
            missing_timeout=args.missing_timeout,
            run_seconds=args.run_seconds,
            keepalive=args.keepalive,
        )
    )


if __name__ == "__main__":
    _main()
