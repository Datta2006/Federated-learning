"""Worker registration, control, and session messages for dynamic AirFed runs.

The original Stage 4 deployment assumed a static list of training node IDs in
``config.json``.  This module adds the small MQTT contract that lets arbitrary
workers register themselves, announce their local dataset and model shape, and
report live training state.  It also defines the dashboard -> coordinator control
commands and the coordinator -> dashboard session/round telemetry.

Only metadata is carried here.  Raw sensor values never leave a worker; the
existing float32 weight-vector and chunk contract remains the only path for
model updates.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from common.mqtt_utils import make_message, utc_now_iso

WORKER_ROLES = {"training", "inference"}
WORKER_STATES = {
    "available",
    "idle",
    "training",
    "uploading",
    "paused",
    "error",
    "offline",
}
CONTROL_COMMANDS = {
    "start_session",
    "pause_session",
    "resume_session",
    "stop_session",
}
SELECTION_STRATEGIES = {"all", "random"}
AGGREGATION_METHODS = {"fedavg"}
TRAINING_MODES = {"fixed", "continuous"}

ROUND_STAGES = [
    ("waiting_for_workers", "Waiting for workers"),
    ("client_selection", "Client selection"),
    ("model_distribution", "Global model distribution"),
    ("local_training", "Local training"),
    ("update_upload", "Update upload"),
    ("update_validation", "Update validation"),
    ("aggregation", "Aggregation"),
    ("model_registration", "Model registration"),
]
ROUND_STAGE_KEYS = [key for key, _label in ROUND_STAGES]

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]+$")


class ProtocolError(ValueError):
    """Raised when a worker/control/session message is malformed."""


def _safe_token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{name} must be a non-empty string")
    if not _SAFE_TOKEN.fullmatch(value):
        raise ProtocolError(
            f"{name} may only contain letters, digits, '_', '.', ':', or '-'; "
            f"got {value!r}"
        )
    return value


def _base(base_topic: str) -> str:
    if not isinstance(base_topic, str) or not base_topic.strip("/"):
        raise ProtocolError("base_topic must be a non-empty string")
    base = base_topic.strip("/")
    if any(part in {"+", "#"} for part in base.split("/")):
        raise ProtocolError("base_topic must not contain MQTT wildcards")
    return base


def _topic(base_topic: str, *parts: str) -> str:
    return "/".join([_base(base_topic), *parts])


def worker_register_topic(base_topic: str, worker_id: str) -> str:
    return _topic(base_topic, "fl", "workers", _safe_token(worker_id, "worker_id"), "register")


def worker_state_topic(base_topic: str, worker_id: str) -> str:
    return _topic(base_topic, "fl", "workers", _safe_token(worker_id, "worker_id"), "state")


def worker_register_filter(base_topic: str) -> str:
    return _topic(base_topic, "fl", "workers") + "/+/register"


def worker_state_filter(base_topic: str) -> str:
    return _topic(base_topic, "fl", "workers") + "/+/state"


def control_topic(base_topic: str) -> str:
    return _topic(base_topic, "fl", "control")


def session_topic(base_topic: str) -> str:
    return _topic(base_topic, "fl", "session")


def round_progress_topic(base_topic: str, round_number: int) -> str:
    return _topic(base_topic, "fl", "round", str(int(round_number)), "progress")


def round_progress_filter(base_topic: str) -> str:
    return _topic(base_topic, "fl", "round") + "/+/progress"


def round_summary_topic(base_topic: str, round_number: int) -> str:
    return _topic(base_topic, "fl", "round", str(int(round_number)), "summary")


def round_summary_filter(base_topic: str) -> str:
    return _topic(base_topic, "fl", "round") + "/+/summary"


def parse_worker_topic(topic: str, base_topic: str) -> tuple[str, str] | None:
    """Return ``(worker_id, leaf)`` for a ``fl/workers/{id}/{leaf}`` topic."""
    pattern = re.compile(
        rf"^{re.escape(_base(base_topic))}/fl/workers/([^/]+)/(register|state)$"
    )
    match = pattern.match(topic)
    return (match.group(1), match.group(2)) if match else None


def parse_round_progress_topic(topic: str, base_topic: str) -> int | None:
    pattern = re.compile(
        rf"^{re.escape(_base(base_topic))}/fl/round/([0-9]+)/progress$"
    )
    match = pattern.match(topic)
    return int(match.group(1)) if match else None


def parse_round_summary_topic(topic: str, base_topic: str) -> int | None:
    pattern = re.compile(
        rf"^{re.escape(_base(base_topic))}/fl/round/([0-9]+)/summary$"
    )
    match = pattern.match(topic)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class TrainingConfig:
    """Validated dashboard-controlled training parameters."""

    mode: str = "fixed"
    rounds: int = 5
    min_workers: int = 1
    max_workers: int | None = None
    local_epochs: int = 1
    deadline_sec: float = 120.0
    selection_strategy: str = "all"
    aggregation_method: str = "fedavg"
    window_hours: int = 24
    learning_rate: float = 0.001
    simulation_workers: int = 0
    launch_workers: bool = True
    worker_role: str = "training"

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> TrainingConfig:
        raw = dict(value or {})
        mode = str(raw.get("mode", "fixed")).strip().lower()
        strategy = str(raw.get("selection_strategy", "all")).strip().lower()
        aggregation = str(raw.get("aggregation_method", "fedavg")).strip().lower()
        role = str(raw.get("worker_role", "training")).strip().lower()
        if mode not in TRAINING_MODES:
            raise ProtocolError(f"mode must be one of {sorted(TRAINING_MODES)}")
        if strategy not in SELECTION_STRATEGIES:
            raise ProtocolError(
                f"selection_strategy must be one of {sorted(SELECTION_STRATEGIES)}"
            )
        if aggregation not in AGGREGATION_METHODS:
            raise ProtocolError(
                f"aggregation_method must be one of {sorted(AGGREGATION_METHODS)}"
            )
        if role not in WORKER_ROLES:
            raise ProtocolError(f"worker_role must be one of {sorted(WORKER_ROLES)}")

        rounds = _positive_int(raw.get("rounds", 5), "rounds")
        min_workers = _positive_int(raw.get("min_workers", 1), "min_workers")
        local_epochs = _positive_int(raw.get("local_epochs", 1), "local_epochs")
        window_hours = _positive_int(raw.get("window_hours", 24), "window_hours")
        deadline = float(raw.get("deadline_sec", 120.0))
        if deadline <= 0:
            raise ProtocolError("deadline_sec must be positive")
        learning_rate = float(raw.get("learning_rate", 0.001))
        if learning_rate <= 0:
            raise ProtocolError("learning_rate must be positive")

        max_raw = raw.get("max_workers")
        max_workers = None if max_raw in (None, "", 0, "0") else _positive_int(
            max_raw, "max_workers"
        )
        if max_workers is not None and max_workers < min_workers:
            raise ProtocolError("max_workers must be greater than or equal to min_workers")

        simulation_raw = raw.get("simulation_workers", 0)
        simulation_workers = 0 if simulation_raw in (None, "") else int(simulation_raw)
        if simulation_workers < 0:
            raise ProtocolError("simulation_workers must be non-negative")
        launch_workers = bool(raw.get("launch_workers", True))
        if mode == "continuous":
            # rounds is ignored for continuous training, but keep a sane value.
            rounds = max(1, rounds)

        return cls(
            mode=mode,
            rounds=rounds,
            min_workers=min_workers,
            max_workers=max_workers,
            local_epochs=local_epochs,
            deadline_sec=deadline,
            selection_strategy=strategy,
            aggregation_method=aggregation,
            window_hours=window_hours,
            learning_rate=learning_rate,
            simulation_workers=simulation_workers,
            launch_workers=launch_workers,
            worker_role=role,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerRecordSeed:
    """Fields accepted in a registration message."""

    worker_id: str
    role: str
    dataset: str = "unknown"
    shard_index: int | None = None
    shard_count: int | None = None
    n_samples: int = 0
    n_val: int = 0
    model: dict[str, Any] = field(default_factory=dict)
    capabilities: dict[str, Any] = field(default_factory=dict)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProtocolError(f"{name} must be a positive integer")
    return value


def build_worker_register(
    worker_id: str,
    *,
    role: str,
    dataset: str,
    n_samples: int,
    n_val: int,
    model: dict[str, Any] | None = None,
    shard_index: int | None = None,
    shard_count: int | None = None,
    capabilities: dict[str, Any] | None = None,
    state: str = "available",
) -> dict[str, Any]:
    """Build the retained registration payload for one worker."""
    worker_id = _safe_token(worker_id, "worker_id")
    if role not in WORKER_ROLES:
        raise ProtocolError(f"role must be one of {sorted(WORKER_ROLES)}")
    if state not in WORKER_STATES:
        raise ProtocolError(f"state must be one of {sorted(WORKER_STATES)}")
    return make_message(
        worker_id,
        message_type="worker_register",
        worker_id=worker_id,
        role=role,
        dataset=str(dataset),
        shard_index=shard_index,
        shard_count=shard_count,
        n_samples=int(n_samples),
        n_val=int(n_val),
        model=dict(model or {}),
        capabilities=dict(capabilities or {}),
        state=state,
    )


def build_worker_state(
    worker_id: str,
    *,
    state: str,
    current_round: int | None = None,
    progress: float | None = None,
    phase: str | None = None,
    detail: str | None = None,
    n_samples: int | None = None,
    model_version: str | None = None,
    update_status: str | None = None,
) -> dict[str, Any]:
    worker_id = _safe_token(worker_id, "worker_id")
    if state not in WORKER_STATES:
        raise ProtocolError(f"state must be one of {sorted(WORKER_STATES)}")
    if progress is not None:
        progress = max(0.0, min(1.0, float(progress)))
    return make_message(
        worker_id,
        message_type="worker_state",
        worker_id=worker_id,
        state=state,
        current_round=current_round,
        progress=progress,
        phase=phase,
        detail=detail,
        n_samples=n_samples,
        model_version=model_version,
        update_status=update_status,
    )


def build_control(command: str, *, config: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    if command not in CONTROL_COMMANDS:
        raise ProtocolError(f"command must be one of {sorted(CONTROL_COMMANDS)}")
    fields: dict[str, Any] = {"message_type": "control", "command": command}
    if config is not None:
        fields["config"] = dict(config)
    fields.update(extra)
    return make_message("dashboard", **fields)


def build_session_state(
    *,
    session_id: str | None,
    state: str,
    config: dict[str, Any] | None,
    round_number: int | None = None,
    completed_rounds: int = 0,
    message: str | None = None,
    latest_model_version: str | None = None,
) -> dict[str, Any]:
    return make_message(
        "flserver",
        message_type="session_state",
        session_id=session_id,
        state=state,
        config=config,
        round=round_number,
        completed_rounds=int(completed_rounds),
        message=message,
        latest_model_version=latest_model_version,
        updated_utc=utc_now_iso(),
    )


def build_round_progress(
    *,
    round_number: int,
    stage: str,
    status: str,
    stages: dict[str, str],
    model_version: str | None,
    selected: list[str],
    accepted: list[str],
    rejected: dict[str, str],
    bytes_up: int,
    bytes_down: int,
    single_client: bool = False,
    detail: str | None = None,
) -> dict[str, Any]:
    if stage not in ROUND_STAGE_KEYS:
        raise ProtocolError(f"unknown round stage {stage!r}")
    return make_message(
        "flserver",
        message_type="round_progress",
        round=int(round_number),
        stage=stage,
        status=status,
        stages=dict(stages),
        model_version=model_version,
        selected=list(selected),
        accepted=list(accepted),
        rejected=dict(rejected),
        bytes_up=int(bytes_up),
        bytes_down=int(bytes_down),
        single_client=bool(single_client),
        detail=detail,
    )


def build_round_summary(
    *,
    round_number: int,
    status: str,
    selected: list[str],
    accepted: list[str],
    rejected: dict[str, str],
    checksums: dict[str, str],
    model_version: str | None,
    evaluated_version: str | None,
    weighted_val_loss: float | None,
    bytes_up: int,
    bytes_down: int,
    seconds: float,
    single_client: bool,
    aggregated: bool,
    config: dict[str, Any] | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """Auditable retained record for one completed/failed dynamic round."""
    return make_message(
        "flserver",
        message_type="round_summary",
        round=int(round_number),
        status=str(status),
        selected=list(selected),
        accepted=list(accepted),
        rejected=dict(rejected),
        checksums=dict(checksums),
        model_version=model_version,
        evaluated_version=evaluated_version,
        weighted_val_loss=weighted_val_loss,
        bytes_up=int(bytes_up),
        bytes_down=int(bytes_down),
        seconds=round(float(seconds), 3),
        single_client=bool(single_client),
        aggregated=bool(aggregated),
        config=dict(config or {}),
        detail=detail,
    )


def validate_worker_register(message: dict[str, Any]) -> WorkerRecordSeed:
    if message.get("message_type") != "worker_register":
        raise ProtocolError("not a worker registration")
    worker_id = _safe_token(message.get("worker_id"), "worker_id")
    role = message.get("role")
    if role not in WORKER_ROLES:
        raise ProtocolError(f"role must be one of {sorted(WORKER_ROLES)}")
    shard_index = message.get("shard_index")
    shard_count = message.get("shard_count")
    if shard_index is not None and (
        isinstance(shard_index, bool) or not isinstance(shard_index, int) or shard_index < 0
    ):
        raise ProtocolError("shard_index must be a non-negative integer")
    if shard_count is not None and (
        isinstance(shard_count, bool) or not isinstance(shard_count, int) or shard_count < 1
    ):
        raise ProtocolError("shard_count must be a positive integer")
    n_samples = int(message.get("n_samples") or 0)
    n_val = int(message.get("n_val") or 0)
    model = message.get("model")
    capabilities = message.get("capabilities")
    return WorkerRecordSeed(
        worker_id=worker_id,
        role=role,
        dataset=str(message.get("dataset") or "unknown"),
        shard_index=shard_index,
        shard_count=shard_count,
        n_samples=n_samples,
        n_val=n_val,
        model=model if isinstance(model, dict) else {},
        capabilities=capabilities if isinstance(capabilities, dict) else {},
    )


def validate_control(message: dict[str, Any]) -> str:
    if message.get("message_type") != "control":
        raise ProtocolError("not a control message")
    command = message.get("command")
    if command not in CONTROL_COMMANDS:
        raise ProtocolError(f"command must be one of {sorted(CONTROL_COMMANDS)}")
    return str(command)
