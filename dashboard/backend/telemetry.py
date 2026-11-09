"""In-memory, read-only telemetry derived from MQTT messages.

This module has no paho dependency on purpose: the parsing/state machine is a
pure seam that tests can drive directly.  ``mqtt_observer.py`` is the small
adapter that feeds it.

Only metadata, checksums, sizes, and status scalars are retained.  Chunk
payloads are verified and immediately discarded; raw sensor readings are never
part of this stream.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

ROUND_STAGE_DEFINITIONS = [
    ("client_selection", "Client selection"),
    ("model_broadcast", "Model broadcast"),
    ("local_training", "Local training"),
    ("weight_upload", "Weight upload"),
    ("update_validation", "Update validation"),
    ("fedavg_aggregation", "FedAvg aggregation"),
    ("model_registration", "Model registration"),
]

TOPIC_CONTRACT = [
    {
        "topic": "{base}/{node}/status",
        "direction": "up",
        "purpose": "Retained online/offline state, including the broker LWT.",
    },
    {
        "topic": "{base}/{node}/health",
        "direction": "up",
        "purpose": "Heartbeat used for stale/offline detection.",
    },
    {
        "topic": "{base}/fl/global/announce",
        "direction": "down",
        "purpose": "Retained global-model metadata and version announcement.",
    },
    {
        "topic": "{base}/fl/global/chunk/{i}",
        "direction": "down",
        "purpose": "Retained global-model weight chunks (16 KiB before base64).",
    },
    {
        "topic": "{base}/fl/round/{r}/start",
        "direction": "down",
        "purpose": "Round invitation with selected nodes and deadline.",
    },
    {
        "topic": "{base}/fl/round/{r}/update/{node}/meta",
        "direction": "up",
        "purpose": "One update's metadata, sample counts, and whole-payload SHA-256.",
    },
    {
        "topic": "{base}/fl/round/{r}/update/{node}/chunk/{i}",
        "direction": "up",
        "purpose": "One update chunk with per-chunk SHA-256.",
    },
    {
        "topic": "{base}/fl/round/{r}/ack/{node}",
        "direction": "down",
        "purpose": "Coordinator accepted/rejected verdict for one update.",
    },
]


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _parse_iso(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return int(value)
    return None


def _safe_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _short_sha(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value[:12]


def _verify_chunk(message: dict[str, Any]) -> bool | None:
    """Verify a chunk checksum locally without keeping the chunk data."""
    encoded = message.get("data")
    expected = message.get("chunk_sha256")
    if not isinstance(encoded, str) or not isinstance(expected, str):
        return None
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return False
    actual = hashlib.sha256(payload).hexdigest()
    return actual == expected.lower()


class TelemetryStore:
    """Bounded live state assembled from observed MQTT traffic."""

    def __init__(
        self,
        *,
        nodes: dict[str, int],
        training_nodes: set[str],
        inference_nodes: set[str],
        base_topic: str,
        heartbeat_sec: float = 10.0,
        max_events: int = 400,
        stale_after_sec: float | None = None,
        round_stale_after_sec: float | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.nodes = dict(nodes)
        self.training_nodes = set(training_nodes)
        self.inference_nodes = set(inference_nodes)
        self.base_topic = base_topic.strip("/")
        self.heartbeat_sec = float(heartbeat_sec)
        self.stale_after_sec = float(
            stale_after_sec
            if stale_after_sec is not None
            else max(3.0 * self.heartbeat_sec, 30.0)
        )
        self.round_stale_after_sec = float(
            round_stale_after_sec
            if round_stale_after_sec is not None
            else max(120.0, 8.0 * self.heartbeat_sec)
        )
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._on_event = on_event
        self._event_id = 0
        self._started_at = time.time()
        self._broker = {
            "connected": False,
            "connected_at": None,
            "last_error": None,
            "last_message_at": None,
            "connection_count": 0,
        }
        self._totals = self._empty_totals()
        self._live_round: dict[str, Any] | None = None
        self._last_model_announce: dict[str, Any] | None = None
        self._nodes_state: dict[str, dict[str, Any]] = {
            node_id: {
                "id": node_id,
                "year": year,
                "role": (
                    "inference" if node_id in self.inference_nodes else "training"
                ),
                "state": None,
                "reason": None,
                "status_at": None,
                "health_at": None,
                "message_ts": None,
                "retained": False,
            }
            for node_id, year in self.nodes.items()
        }

    # --------------------------------------------------------------- broker
    def set_broker_state(
        self, connected: bool, *, error: str | None = None, now: float | None = None
    ) -> None:
        now = time.time() if now is None else now
        with self._lock:
            was_connected = self._broker["connected"]
            self._broker["connected"] = bool(connected)
            self._broker["last_error"] = error
            if connected and not was_connected:
                self._broker["connected_at"] = now
                self._broker["connection_count"] += 1
                self._totals = self._empty_totals()
            self._append_event(
                {
                    "at": _iso(now),
                    "topic": "observer",
                    "kind": "observer_connected" if connected else "observer_disconnected",
                    "detail": (
                        "Dashboard observer connected to the broker"
                        if connected
                        else f"Dashboard observer disconnected: {error or 'unknown'}"
                    ),
                    "status": "accepted" if connected else "rejected",
                },
                now,
            )

    @staticmethod
    def _empty_totals() -> dict[str, Any]:
        return {
            "bytes_up": 0,
            "bytes_down": 0,
            "messages": 0,
            "chunks": 0,
            "chunk_bytes": 0,
            "checksum_ok": 0,
            "checksum_bad": 0,
            "acks_accepted": 0,
            "acks_rejected": 0,
        }

    # ---------------------------------------------------------------- ingest
    def ingest(
        self,
        topic: str,
        payload: bytes | bytearray | str | dict[str, Any],
        *,
        retain: bool = False,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        """Consume one MQTT message and return the event added to the feed."""
        now = time.time() if now is None else now
        if isinstance(payload, (bytes, bytearray)):
            raw = bytes(payload)
            size = len(raw)
            try:
                message = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = None
        elif isinstance(payload, str):
            size = len(payload.encode("utf-8"))
            try:
                message = json.loads(payload)
            except json.JSONDecodeError:
                message = None
        else:
            message = payload
            size = len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

        if not isinstance(message, dict):
            return self._record_unknown(topic, retain, size, now, "invalid JSON payload")

        with self._lock:
            self._broker["last_message_at"] = now
            event = self._classify(topic, message, retain, size, now)
            if event is None:
                event = self._base_event(
                    topic, "other", retain, size, now, detail="Unrecognised topic"
                )
            self._count(event, size)
            self._append_event(event, now)
            return dict(event)

    def _record_unknown(
        self, topic: str, retain: bool, size: int, now: float, detail: str
    ) -> dict[str, Any]:
        with self._lock:
            self._broker["last_message_at"] = now
            event = self._base_event(
                topic, "invalid", retain, size, now, detail=detail
            )
            self._count(event, size)
            self._append_event(event, now)
            return dict(event)

    def _base_event(
        self,
        topic: str,
        kind: str,
        retain: bool,
        size: int,
        now: float,
        *,
        detail: str,
        node_id: str | None = None,
        round_number: int | None = None,
        model_version: str | None = None,
        status: str | None = None,
        index: int | None = None,
        chunks: int | None = None,
        checksum: str | None = None,
        checksum_ok: bool | None = None,
    ) -> dict[str, Any]:
        return {
            "id": self._event_id + 1,
            "at": _iso(now),
            "topic": topic,
            "kind": kind,
            "node_id": node_id,
            "round": round_number,
            "model_version": model_version,
            "status": status,
            "index": index,
            "chunks": chunks,
            "size_bytes": int(size),
            "checksum": _short_sha(checksum),
            "checksum_ok": checksum_ok,
            "retained": bool(retain),
            "detail": detail,
        }

    def _append_event(self, event: dict[str, Any], now: float) -> None:
        self._event_id += 1
        event["id"] = self._event_id
        event.setdefault("at", _iso(now))
        self._events.append(event)
        callback = self._on_event
        if callback is not None:
            try:
                callback(dict(event))
            except Exception:  # pragma: no cover - observer must stay alive
                pass

    def _count(self, event: dict[str, Any], size: int) -> None:
        kind = event["kind"]
        direction = event.get("direction")
        self._totals["messages"] += 1
        if direction == "up":
            self._totals["bytes_up"] += size
        elif direction == "down":
            self._totals["bytes_down"] += size
        if kind in {"update_chunk", "model_chunk"}:
            self._totals["chunks"] += 1
            self._totals["chunk_bytes"] += size
            if event.get("checksum_ok") is True:
                self._totals["checksum_ok"] += 1
            elif event.get("checksum_ok") is False:
                self._totals["checksum_bad"] += 1
        if kind == "ack_accepted":
            self._totals["acks_accepted"] += 1
        elif kind == "ack_rejected":
            self._totals["acks_rejected"] += 1
        if self._live_round is not None:
            if direction == "up":
                self._live_round["bytes_up"] += size
            elif direction == "down":
                self._live_round["bytes_down"] += size

    def _classify(
        self,
        topic: str,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any] | None:
        base = re.escape(self.base_topic)
        node_match = re.match(rf"^{base}/([^/]+)/(status|health)$", topic)
        if node_match:
            node_id, leaf = node_match.group(1), node_match.group(2)
            return self._handle_node(node_id, leaf, message, retain, size, now)

        if topic == f"{self.base_topic}/fl/global/announce":
            return self._handle_global_announce(message, retain, size, now)

        chunk_match = re.match(rf"^{base}/fl/global/chunk/(\d+)$", topic)
        if chunk_match:
            return self._handle_global_chunk(
                int(chunk_match.group(1)), message, retain, size, now
            )

        start_match = re.match(rf"^{base}/fl/round/(\d+)/start$", topic)
        if start_match:
            return self._handle_round_start(
                int(start_match.group(1)), message, retain, size, now
            )

        meta_match = re.match(
            rf"^{base}/fl/round/(\d+)/update/([^/]+)/meta$", topic
        )
        if meta_match:
            return self._handle_update_meta(
                int(meta_match.group(1)),
                meta_match.group(2),
                message,
                retain,
                size,
                now,
            )

        update_chunk_match = re.match(
            rf"^{base}/fl/round/(\d+)/update/([^/]+)/chunk/(\d+)$", topic
        )
        if update_chunk_match:
            return self._handle_update_chunk(
                int(update_chunk_match.group(1)),
                update_chunk_match.group(2),
                int(update_chunk_match.group(3)),
                message,
                retain,
                size,
                now,
            )

        ack_match = re.match(rf"^{base}/fl/round/(\d+)/ack/([^/]+)$", topic)
        if ack_match:
            return self._handle_ack(
                int(ack_match.group(1)),
                ack_match.group(2),
                message,
                retain,
                size,
                now,
            )

        return None

    # --------------------------------------------------------------- nodes
    def _handle_node(
        self,
        node_id: str,
        leaf: str,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        state = self._nodes_state.setdefault(
            node_id,
            {
                "id": node_id,
                "year": self.nodes.get(node_id),
                "role": (
                    "inference" if node_id in self.inference_nodes else "training"
                ),
                "state": None,
                "reason": None,
                "status_at": None,
                "health_at": None,
                "message_ts": None,
                "retained": False,
            },
        )
        state["message_ts"] = message.get("ts")
        state["retained"] = retain
        if leaf == "status":
            status = message.get("state")
            state["state"] = status if status in {"online", "offline"} else None
            state["reason"] = message.get("reason")
            state["status_at"] = now
            detail = f"{node_id} reported {state or 'unknown'} state"
            if state == "offline" and message.get("reason"):
                detail += f" ({message.get('reason')})"
            kind = "status"
            event_status = "accepted" if state == "online" else "rejected"
        else:
            state["health_at"] = now
            backend = message.get("backend")
            detail = f"{node_id} heartbeat"
            if backend:
                detail += f" · backend={backend}"
            kind = "health"
            event_status = "accepted"
        return {
            **self._base_event(
                f"{self.base_topic}/{node_id}/{leaf}",
                kind,
                retain,
                size,
                now,
                detail=detail,
                node_id=node_id,
                status=event_status,
            ),
            "direction": "up",
        }

    # -------------------------------------------------------------- global
    def _handle_global_announce(
        self,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        version = message.get("model_version")
        round_number = _safe_int(message.get("federated_round"))
        chunks = _safe_int(message.get("chunks"))
        checksum = message.get("sha256")
        self._last_model_announce = {
            "model_version": version,
            "federated_round": round_number,
            "chunks": chunks,
            "sha256": checksum,
            "size": _safe_int(message.get("size")),
            "at": _iso(now),
            "retained": retain,
        }
        if (
            self._live_round is not None
            and round_number is not None
            and round_number == self._live_round.get("round")
            and version == f"v{round_number:04d}"
        ):
            self._live_round["registered_version"] = version
            self._live_round["registration_at"] = now
            self._live_round["last_event_at"] = now

        detail = f"Global model {version or 'unknown'} announced"
        if round_number is not None:
            detail += f" · federated round {round_number}"
        if chunks is not None:
            detail += f" · {chunks} chunks"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/global/announce",
                "model_announce",
                retain,
                size,
                now,
                detail=detail,
                model_version=str(version) if version else None,
                round_number=round_number,
                chunks=chunks,
                checksum=str(checksum) if checksum else None,
            ),
            "direction": "down",
        }

    def _handle_global_chunk(
        self,
        index: int,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        checksum_ok = _verify_chunk(message)
        version = message.get("model_version")
        chunks = _safe_int(message.get("chunks"))
        detail = f"Global model chunk {index}"
        if chunks is not None:
            detail += f"/{chunks}"
        detail += f" · {size:,} B"
        if checksum_ok is False:
            detail += " · checksum mismatch"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/global/chunk/{index}",
                "model_chunk",
                retain,
                size,
                now,
                detail=detail,
                model_version=str(version) if version else None,
                index=index,
                chunks=chunks,
                checksum=message.get("chunk_sha256"),
                checksum_ok=checksum_ok,
            ),
            "direction": "down",
        }

    # --------------------------------------------------------------- round
    def _ensure_round(self, round_number: int, now: float) -> dict[str, Any]:
        if self._live_round is None or self._live_round.get("round") != round_number:
            self._live_round = {
                "round": round_number,
                "model_version": None,
                "selected": [],
                "started_at": now,
                "last_event_at": now,
                "upload_nodes": set(),
                "chunk_indices": {},
                "acks": {},
                "reasons": {},
                "bytes_up": 0,
                "bytes_down": 0,
                "registered_version": None,
                "registration_at": None,
                "source": "mqtt",
            }
        return self._live_round

    def _handle_round_start(
        self,
        round_number: int,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        live = self._ensure_round(round_number, now)
        live["model_version"] = message.get("model_version")
        live["selected"] = [
            str(node) for node in message.get("selected_nodes", []) if str(node)
        ]
        live["started_at"] = _parse_iso(message.get("ts")) or now
        live["last_event_at"] = now
        live["source"] = "mqtt"
        detail = f"Round {round_number} started"
        if live["model_version"]:
            detail += f" · {live['model_version']}"
        if live["selected"]:
            detail += f" · {len(live['selected'])} selected"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/round/{round_number}/start",
                "round_start",
                retain,
                size,
                now,
                detail=detail,
                round_number=round_number,
                model_version=str(live["model_version"])
                if live["model_version"]
                else None,
            ),
            "direction": "down",
        }

    def _handle_update_meta(
        self,
        round_number: int,
        node_id: str,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        live = self._ensure_round(round_number, now)
        live["last_event_at"] = now
        live["upload_nodes"].add(node_id)
        n_samples = _safe_int(message.get("n_samples"))
        val_loss = _safe_float(message.get("val_loss"))
        detail = f"{node_id} update metadata"
        if n_samples is not None:
            detail += f" · {n_samples:,} samples"
        if val_loss is not None:
            detail += f" · val {val_loss:.6f}"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/round/{round_number}/update/{node_id}/meta",
                "update_meta",
                retain,
                size,
                now,
                detail=detail,
                node_id=node_id,
                round_number=round_number,
                model_version=(
                    str(message.get("model_version"))
                    if message.get("model_version")
                    else None
                ),
                chunks=_safe_int(message.get("chunks")),
                checksum=message.get("sha256"),
            ),
            "direction": "up",
        }

    def _handle_update_chunk(
        self,
        round_number: int,
        node_id: str,
        index: int,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        live = self._ensure_round(round_number, now)
        live["last_event_at"] = now
        live["upload_nodes"].add(node_id)
        indices = live["chunk_indices"].setdefault(node_id, set())
        indices.add(index)
        checksum_ok = _verify_chunk(message)
        chunks = _safe_int(message.get("chunks"))
        detail = f"{node_id} upload chunk {index}"
        if chunks is not None:
            detail += f"/{chunks}"
        detail += f" · {size:,} B"
        if checksum_ok is True:
            detail += " · checksum verified"
        elif checksum_ok is False:
            detail += " · checksum mismatch"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/round/{round_number}/update/{node_id}/chunk/{index}",
                "update_chunk",
                retain,
                size,
                now,
                detail=detail,
                node_id=node_id,
                round_number=round_number,
                index=index,
                chunks=chunks,
                checksum=message.get("chunk_sha256"),
                checksum_ok=checksum_ok,
            ),
            "direction": "up",
        }

    def _handle_ack(
        self,
        round_number: int,
        node_id: str,
        message: dict[str, Any],
        retain: bool,
        size: int,
        now: float,
    ) -> dict[str, Any]:
        live = self._ensure_round(round_number, now)
        live["last_event_at"] = now
        status = message.get("status")
        status = status if status in {"accepted", "rejected"} else "rejected"
        live["acks"][node_id] = status
        if message.get("reason"):
            live["reasons"][node_id] = str(message.get("reason"))
        kind = "ack_accepted" if status == "accepted" else "ack_rejected"
        detail = f"{node_id} update {status}"
        if message.get("reason"):
            detail += f" · {message.get('reason')}"
        return {
            **self._base_event(
                f"{self.base_topic}/fl/round/{round_number}/ack/{node_id}",
                kind,
                retain,
                size,
                now,
                detail=detail,
                node_id=node_id,
                round_number=round_number,
                status=status,
                model_version=(
                    str(message.get("model_version"))
                    if message.get("model_version")
                    else None
                ),
                checksum=message.get("sha256"),
            ),
            "direction": "down",
        }

    # -------------------------------------------------------------- status
    def _node_view(self, node_id: str, now: float) -> dict[str, Any]:
        state = self._nodes_state[node_id]
        observed = state.get("status_at")
        healthy = state.get("health_at")
        if state.get("state") is None:
            status = "unknown"
        elif state.get("state") == "offline":
            status = "offline"
        else:
            fresh_health = healthy is not None and now - healthy <= self.stale_after_sec
            fresh_status = observed is not None and now - observed <= self.stale_after_sec
            status = "online" if (fresh_health or fresh_status) else "stale"
        last_seen = max([value for value in (observed, healthy) if value is not None], default=None)
        return {
            "id": node_id,
            "year": state.get("year"),
            "role": state.get("role"),
            "status": status,
            "reported_state": state.get("state"),
            "reason": state.get("reason"),
            "last_seen": _iso(last_seen),
            "last_health": _iso(healthy),
            "message_ts": state.get("message_ts"),
            "retained": state.get("retained", False),
            "source": "mqtt" if observed is not None else "none",
        }

    def _round_view(self, now: float) -> dict[str, Any] | None:
        live = self._live_round
        if live is None:
            return None
        selected = list(live["selected"])
        uploads = sorted(live["upload_nodes"])
        acks = dict(live["acks"])
        accepted = [node for node, status in acks.items() if status == "accepted"]
        rejected = [node for node, status in acks.items() if status == "rejected"]
        expected = len(selected) if selected else len(uploads)
        received = len(uploads)
        ack_count = len(acks)
        registered = live.get("registered_version") is not None
        idle_seconds = now - float(live.get("last_event_at") or now)
        is_live = (
            self._broker["connected"]
            and idle_seconds <= self.round_stale_after_sec
            and not registered
        )

        if registered:
            phase = "completed"
        elif expected and ack_count >= expected:
            phase = "aggregating"
        elif ack_count:
            phase = "update_validation"
        elif received:
            phase = "weight_upload"
        else:
            phase = "local_training"

        stages = self._stage_view(
            selected=selected,
            uploads=uploads,
            acks=acks,
            registered=registered,
        )
        return {
            "round": live["round"],
            "model_version": live.get("model_version"),
            "selected": selected,
            "received": received,
            "upload_nodes": uploads,
            "acks": acks,
            "accepted": accepted,
            "rejected": rejected,
            "reasons": dict(live["reasons"]),
            "registered_version": live.get("registered_version"),
            "started_at": _iso(live.get("started_at")),
            "last_event_at": _iso(live.get("last_event_at")),
            "bytes_up": int(live["bytes_up"]),
            "bytes_down": int(live["bytes_down"]),
            "phase": phase,
            "phase_label": {
                "local_training": "Local training",
                "weight_upload": "Weight upload",
                "update_validation": "Update validation",
                "aggregating": "FedAvg aggregation",
                "completed": "Model registered",
            }.get(phase, phase),
            "is_live": is_live,
            "idle_seconds": round(idle_seconds, 1),
            "stages": stages,
            "source": "mqtt",
        }

    def _stage_view(
        self,
        *,
        selected: list[str],
        uploads: list[str],
        acks: dict[str, str],
        registered: bool,
    ) -> list[dict[str, str]]:
        expected = len(selected) if selected else len(uploads)
        # A node that already has an ack has finished uploading, whether the
        # coordinator accepted or rejected the update.
        resolved = set(uploads).union(acks)
        upload_complete = bool(expected) and len(resolved) >= expected
        ack_complete = bool(expected) and len(acks) >= expected
        any_upload = bool(uploads)
        any_ack = bool(acks)
        statuses = {
            "client_selection": "complete" if selected else "pending",
            "model_broadcast": "complete",
            "local_training": (
                "complete" if any_upload or registered else "active"
            ),
            "weight_upload": (
                "complete"
                if upload_complete or registered
                else ("active" if any_upload else "pending")
            ),
            "update_validation": (
                "complete"
                if ack_complete or registered
                else ("active" if any_ack else "pending")
            ),
            "fedavg_aggregation": (
                "complete"
                if registered
                else ("active" if ack_complete else "pending")
            ),
            "model_registration": (
                "complete"
                if registered
                else ("active" if ack_complete else "pending")
            ),
        }
        return [
            {"key": key, "label": label, "status": statuses[key]}
            for key, label in ROUND_STAGE_DEFINITIONS
        ]

    def status_payload(
        self,
        registry: dict[str, Any],
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else now
        with self._lock:
            nodes = [self._node_view(node_id, now) for node_id in self.nodes]
            live_round = self._round_view(now)
            latest = registry.get("latest") or {}
            historical_round = None
            rounds = registry.get("rounds") or []
            if live_round is None and rounds:
                last = rounds[-1]
                historical_round = {
                    "round": last.get("round"),
                    "model_version": last.get("model_version"),
                    "selected": last.get("selected", []),
                    "received": last.get("received", 0),
                    "upload_nodes": last.get("selected", []),
                    "acks": {},
                    "accepted": last.get("selected", [])[
                        : int(last.get("received") or 0)
                    ],
                    "rejected": last.get("dropped_nodes", []),
                    "reasons": {},
                    "registered_version": last.get("model_version"),
                    "started_at": None,
                    "last_event_at": None,
                    "bytes_up": last.get("bytes_up", 0),
                    "bytes_down": last.get("bytes_down", 0),
                    "phase": "completed",
                    "phase_label": "Round registered",
                    "is_live": False,
                    "idle_seconds": None,
                    "stages": [
                        {"key": key, "label": label, "status": "complete"}
                        for key, label in ROUND_STAGE_DEFINITIONS
                    ],
                    "source": "registry",
                }

            stale_round = bool(live_round) and not live_round.get("is_live")
            return {
                "server_time": _iso(now),
                "data_source": (
                    "live_mqtt"
                    if self._broker["connected"] and self._events
                    else ("registry_only" if registry.get("available") else "unavailable")
                ),
                "broker": {
                    "connected": self._broker["connected"],
                    "host": None,
                    "port": None,
                    "last_error": self._broker["last_error"],
                    "connected_at": _iso(self._broker["connected_at"]),
                    "last_message_at": _iso(self._broker["last_message_at"]),
                    "connection_count": self._broker["connection_count"],
                },
                "observer": {
                    "started_at": _iso(self._started_at),
                    "events": len(self._events),
                    "stale_after_sec": self.stale_after_sec,
                    "round_stale_after_sec": self.round_stale_after_sec,
                },
                "nodes": nodes,
                "current_round": live_round or historical_round,
                "round_is_live": bool(live_round and live_round.get("is_live")),
                "round_is_stale": stale_round,
                "latest_model": latest,
                "registry": {
                    "available": registry.get("available", False),
                    "path": registry.get("registry_path"),
                    "source": registry.get("source"),
                    "round_count": registry.get("round_count"),
                },
                "provenance": {
                    "live": "MQTT observer",
                    "historical": "Coordinator registry (rounds.csv / latest.json)",
                    "note": (
                        "The dashboard is a separate read-only subscriber. "
                        "It never publishes commands or model updates."
                    ),
                },
            }

    def events(self, limit: int = 120) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(event) for event in list(self._events)[-limit:][::-1]]

    def communication_payload(
        self,
        registry: dict[str, Any],
        *,
        limit: int = 120,
        now: float | None = None,
    ) -> dict[str, Any]:
        now = time.time() if now is None else now
        with self._lock:
            totals = dict(self._totals)
            live_round = self._round_view(now)
            latest = registry.get("latest") or {}
            rounds = registry.get("rounds") or []
            history = [
                {
                    "round": row.get("round"),
                    "bytes_up": row.get("bytes_up"),
                    "bytes_down": row.get("bytes_down"),
                    "received": row.get("received"),
                    "selected": len(row.get("selected") or []),
                    "dropped_nodes": row.get("dropped_nodes", []),
                    "round_time_sec": row.get("round_time_sec"),
                }
                for row in rounds
            ]
            return {
                "server_time": _iso(now),
                "broker": {
                    "connected": self._broker["connected"],
                    "last_error": self._broker["last_error"],
                    "connected_at": _iso(self._broker["connected_at"]),
                    "last_message_at": _iso(self._broker["last_message_at"]),
                },
                "observed": totals,
                "live_round": live_round,
                "history": history,
                "last_model_announce": self._last_model_announce,
                "model_transfer": {
                    "model_version": latest.get("model_version"),
                    "parameters": latest.get("parameters"),
                    "bytes": registry.get("latest_model_bytes"),
                    "chunk_size": registry.get("chunk_size"),
                    "chunks": registry.get("chunk_count"),
                    "source": "registry",
                },
                "acks": {
                    "accepted": totals["acks_accepted"],
                    "rejected": totals["acks_rejected"],
                    "rejected_events": [
                        event
                        for event in list(self._events)[-limit:]
                        if event.get("kind") == "ack_rejected"
                    ][::-1],
                },
                "events": [dict(event) for event in list(self._events)[-limit:][::-1]],
                "topic_contract": [
                    {
                        **item,
                        "topic": item["topic"].format(
                            base=self.base_topic, node="{node}", r="{r}", i="{i}"
                        ),
                    }
                    for item in TOPIC_CONTRACT
                ],
                "provenance": {
                    "observed": (
                        "Bytes and events measured by the dashboard's own "
                        "MQTT subscriber since it connected."
                    ),
                    "history": (
                        "Round byte totals read from the coordinator's rounds.csv."
                    ),
                    "note": (
                        "Chunk bodies are verified and discarded. Only metadata, "
                        "sizes, and checksum verdicts are kept."
                    ),
                },
            }
