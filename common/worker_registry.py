"""Heartbeat-expiring registry of dynamically registered federated workers.

A retained registration message proves that a worker process once existed; it
does **not** prove that it is online now.  Liveness therefore comes only from
fresh ``worker_state`` heartbeats, with a bounded expiry window.  This keeps an
old retained status from being displayed as an active worker after the process
has gone away.

The registry is deliberately transport-agnostic and clock-injectable so the
expiry rules can be unit-tested without MQTT or real sleeping.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from common.worker_protocol import (
    ProtocolError,
    validate_worker_register,
)

MODEL_KEYS = ("architecture", "window_hours", "n_features", "pool_size")
BUSY_STATES = {"training", "uploading"}
AVAILABLE_STATES = {"available", "idle", "training", "uploading"}
NON_SELECTABLE_STATES = {"paused", "error", "offline"}


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def model_compatibility(
    worker_model: dict[str, Any], expected_model: dict[str, Any]
) -> tuple[bool, str | None]:
    """Compare a worker's model description with the coordinator's model.

    Only architecture-defining keys matter for whether a weight vector can be
    aggregated.  An empty coordinator description (dummy/legacy mode) accepts
    any worker.
    """
    if not expected_model:
        return True, None
    if not worker_model:
        return False, "worker did not advertise a model description"
    reasons: list[str] = []
    for key in MODEL_KEYS:
        if key not in expected_model:
            continue
        if key not in worker_model:
            reasons.append(f"missing {key}")
            continue
        if worker_model[key] != expected_model[key]:
            reasons.append(
                f"{key}={worker_model[key]!r} (coordinator {expected_model[key]!r})"
            )
    if reasons:
        return False, "; ".join(reasons)
    return True, None


@dataclass
class WorkerEntry:
    worker_id: str
    role: str = "training"
    dataset: str = "unknown"
    shard_index: int | None = None
    shard_count: int | None = None
    n_samples: int = 0
    n_val: int = 0
    model: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0
    last_seen: float = 0.0
    status_at: float | None = None
    state: str = "available"
    current_round: int | None = None
    progress: float | None = None
    phase: str | None = None
    detail: str | None = None
    update_status: str | None = None
    model_version: str | None = None
    online: bool = False
    model_compatible: bool = True
    model_mismatch: str | None = None
    registration_count: int = 1

    def to_dict(self, now: float) -> dict[str, Any]:
        age = None if not self.last_seen else max(0.0, now - self.last_seen)
        return {
            "id": self.worker_id,
            "worker_id": self.worker_id,
            "role": self.role,
            "dataset": self.dataset,
            "shard_index": self.shard_index,
            "shard_count": self.shard_count,
            "n_samples": int(self.n_samples),
            "n_val": int(self.n_val),
            "model": dict(self.model),
            "capabilities": dict(self.capabilities),
            "state": self.state,
            "online": bool(self.online),
            "connection": "online" if self.online else "offline",
            "last_seen": _iso(self.last_seen) if self.last_seen else None,
            "last_seen_age_sec": None if age is None else round(age, 1),
            "registered_at": _iso(self.registered_at) if self.registered_at else None,
            "current_round": self.current_round,
            "progress": self.progress,
            "phase": self.phase,
            "detail": self.detail,
            "update_status": self.update_status,
            "model_version": self.model_version,
            "model_compatible": bool(self.model_compatible),
            "model_mismatch": self.model_mismatch,
            "registration_count": self.registration_count,
            "selectable": bool(
                self.online
                and self.role == "training"
                and self.model_compatible
                and self.state not in NON_SELECTABLE_STATES
            ),
        }


class WorkerRegistry:
    """In-memory worker presence and training state."""

    def __init__(
        self,
        *,
        expiry_sec: float = 45.0,
        expected_model: dict[str, Any] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if expiry_sec <= 0:
            raise ValueError("expiry_sec must be positive")
        self.expiry_sec = float(expiry_sec)
        self.expected_model = dict(expected_model or {})
        self._clock = clock or time.monotonic
        self._workers: dict[str, WorkerEntry] = {}

    # ------------------------------------------------------------- ingest
    def register(
        self, message: dict[str, Any], *, now: float | None = None
    ) -> WorkerEntry:
        """Apply a ``worker_register`` payload and refresh its heartbeat."""
        now = self._clock() if now is None else now
        seed = validate_worker_register(message)
        entry = self._workers.get(seed.worker_id)
        compatible, mismatch = model_compatibility(seed.model, self.expected_model)
        if entry is None:
            entry = WorkerEntry(
                worker_id=seed.worker_id,
                registered_at=now,
                last_seen=now,
                online=True,
            )
            self._workers[seed.worker_id] = entry
        else:
            entry.registration_count += 1
            entry.last_seen = now
        entry.role = seed.role
        entry.dataset = seed.dataset
        entry.shard_index = seed.shard_index
        entry.shard_count = seed.shard_count
        entry.n_samples = seed.n_samples
        entry.n_val = seed.n_val
        entry.model = dict(seed.model)
        entry.capabilities = dict(seed.capabilities)
        entry.model_compatible = compatible
        entry.model_mismatch = mismatch
        # A fresh registration is evidence of life, but only heartbeat/state
        # messages keep the worker online after the expiry window.
        entry.online = True
        if entry.state == "offline":
            entry.state = "available"
        return entry

    def state(
        self, message: dict[str, Any], *, now: float | None = None
    ) -> WorkerEntry | None:
        """Apply a ``worker_state`` heartbeat for a registered worker."""
        now = self._clock() if now is None else now
        worker_id = message.get("worker_id")
        if not isinstance(worker_id, str):
            return None
        entry = self._workers.get(worker_id)
        if entry is None:
            # Unknown heartbeats cannot be classified as training or inference.
            # Ignore them until the retained registration arrives.
            return None
        state = message.get("state")
        if not isinstance(state, str):
            return None
        entry.state = state
        entry.last_seen = now
        entry.status_at = now
        entry.online = state != "offline"
        entry.current_round = _int_or_none(message.get("current_round"))
        entry.progress = _float_or_none(message.get("progress"))
        entry.phase = _str_or_none(message.get("phase"))
        entry.detail = _str_or_none(message.get("detail"))
        entry.update_status = _str_or_none(message.get("update_status"))
        entry.model_version = _str_or_none(message.get("model_version"))
        if isinstance(message.get("n_samples"), int):
            entry.n_samples = int(message["n_samples"])
        if isinstance(message.get("n_val"), int):
            entry.n_val = int(message["n_val"])
        return entry

    def heartbeat(self, worker_id: str, *, now: float | None = None) -> None:
        now = self._clock() if now is None else now
        entry = self._workers.get(worker_id)
        if entry is None:
            return
        entry.last_seen = now
        if entry.state == "offline":
            entry.state = "available"
        entry.online = True

    def expire(self, *, now: float | None = None) -> list[str]:
        """Mark workers offline when their last heartbeat is too old."""
        now = self._clock() if now is None else now
        expired: list[str] = []
        for entry in self._workers.values():
            if not entry.online:
                continue
            if now - entry.last_seen > self.expiry_sec:
                entry.online = False
                entry.state = "offline"
                entry.progress = None
                entry.phase = "heartbeat_expired"
                expired.append(entry.worker_id)
        return expired

    # ------------------------------------------------------------ querying
    def get(self, worker_id: str) -> WorkerEntry | None:
        return self._workers.get(worker_id)

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        now = self._clock() if now is None else now
        self.expire(now=now)
        workers = [
            entry.to_dict(now)
            for entry in sorted(
                self._workers.values(), key=lambda item: item.worker_id
            )
        ]
        counts = self.counts(now=now, workers=workers)
        return {
            "workers": workers,
            "counts": counts,
            "expiry_sec": self.expiry_sec,
            "expected_model": dict(self.expected_model),
        }

    def counts(
        self,
        *,
        now: float | None = None,
        workers: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        del now
        items = workers if workers is not None else self.snapshot()["workers"]
        return {
            "total": len(items),
            "online": sum(1 for item in items if item["online"]),
            "offline": sum(1 for item in items if not item["online"]),
            "training": sum(
                1 for item in items if item["role"] == "training" and item["online"]
            ),
            "inference": sum(
                1 for item in items if item["role"] == "inference" and item["online"]
            ),
            "available": sum(
                1
                for item in items
                if item["online"]
                and item["role"] == "training"
                and item["state"] in AVAILABLE_STATES
                and item["model_compatible"]
            ),
            "busy": sum(
                1
                for item in items
                if item["online"] and item["state"] in BUSY_STATES
            ),
            "incompatible": sum(
                1 for item in items if not item["model_compatible"]
            ),
        }

    def online_workers(self, *, now: float | None = None) -> list[WorkerEntry]:
        now = self._clock() if now is None else now
        self.expire(now=now)
        return [entry for entry in self._workers.values() if entry.online]

    def selectable_training_workers(
        self, *, now: float | None = None
    ) -> list[WorkerEntry]:
        return [
            entry
            for entry in self.online_workers(now=now)
            if entry.role == "training"
            and entry.model_compatible
            and entry.state not in NON_SELECTABLE_STATES
        ]

    def set_round_state(
        self,
        worker_id: str,
        *,
        state: str,
        round_number: int | None = None,
        phase: str | None = None,
        now: float | None = None,
    ) -> None:
        entry = self._workers.get(worker_id)
        if entry is None:
            return
        entry.state = state
        entry.phase = phase
        entry.last_seen = self._clock() if now is None else now
        entry.online = state != "offline"
        if round_number is not None:
            entry.current_round = round_number


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = [
    "ProtocolError",
    "WorkerEntry",
    "WorkerRegistry",
    "model_compatibility",
]
