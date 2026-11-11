"""Unit tests for the heartbeat-expiring dynamic worker registry."""

from __future__ import annotations

from common.worker_protocol import build_worker_register, build_worker_state
from common.worker_registry import WorkerRegistry, model_compatibility

MODEL = {"architecture": "cnn_rnn", "window_hours": 24, "n_features": 5}


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _register(worker_id: str, *, role: str = "training", model=None, samples: int = 100):
    return build_worker_register(
        worker_id,
        role=role,
        dataset="unit",
        n_samples=samples,
        n_val=10,
        model=MODEL if model is None else model,
    )


def test_retained_status_without_heartbeat_expires() -> None:
    clock = Clock()
    registry = WorkerRegistry(expiry_sec=10.0, clock=clock)
    registry.register(_register("sim-1"))
    assert registry.get("sim-1").online is True

    clock.advance(5.0)
    assert registry.expire() == []
    assert registry.snapshot()["counts"]["online"] == 1

    clock.advance(6.0)
    assert registry.expire() == ["sim-1"]
    snapshot = registry.snapshot()
    worker = snapshot["workers"][0]
    assert worker["online"] is False
    assert worker["state"] == "offline"
    assert worker["selectable"] is False
    assert worker["phase"] == "heartbeat_expired"
    assert snapshot["counts"]["online"] == 0


def test_inference_workers_are_never_selectable() -> None:
    clock = Clock()
    registry = WorkerRegistry(clock=clock)
    registry.register(_register("train-1", role="training"))
    registry.register(_register("infer-1", role="inference"))
    registry.state(
        build_worker_state("infer-1", state="available"), now=clock.now
    )
    registry.state(
        build_worker_state("train-1", state="available"), now=clock.now
    )

    selectable = [entry.worker_id for entry in registry.selectable_training_workers()]
    assert selectable == ["train-1"]
    counts = registry.snapshot()["counts"]
    assert counts["training"] == 1
    assert counts["inference"] == 1
    assert counts["available"] == 1


def test_paused_and_offline_states_are_not_selectable() -> None:
    clock = Clock()
    registry = WorkerRegistry(clock=clock)
    registry.register(_register("sim-1"))
    registry.state(build_worker_state("sim-1", state="paused"), now=clock.now)
    assert registry.selectable_training_workers() == []
    registry.state(build_worker_state("sim-1", state="available"), now=clock.now)
    assert len(registry.selectable_training_workers()) == 1
    registry.state(build_worker_state("sim-1", state="offline"), now=clock.now)
    assert registry.selectable_training_workers() == []
    assert registry.get("sim-1").online is False


def test_model_mismatch_is_excluded_and_reasoned() -> None:
    clock = Clock()
    registry = WorkerRegistry(clock=clock, expected_model=MODEL)
    registry.register(
        _register("old-1", model={"architecture": "cnn_rnn", "window_hours": 12})
    )
    registry.register(_register("ok-1"))

    old = registry.get("old-1")
    assert old.model_compatible is False
    assert "window_hours" in (old.model_mismatch or "")
    assert [entry.worker_id for entry in registry.selectable_training_workers()] == [
        "ok-1"
    ]
    snapshot = registry.snapshot()
    assert snapshot["counts"]["incompatible"] == 1
    assert snapshot["counts"]["available"] == 1


def test_state_before_registration_is_ignored() -> None:
    clock = Clock()
    registry = WorkerRegistry(clock=clock)
    assert registry.state(build_worker_state("ghost", state="available")) is None
    assert registry.get("ghost") is None


def test_reregistration_refreshes_heartbeat() -> None:
    clock = Clock()
    registry = WorkerRegistry(expiry_sec=10.0, clock=clock)
    registry.register(_register("sim-1"))
    clock.advance(9.0)
    registry.register(_register("sim-1", samples=250))
    clock.advance(9.0)
    assert registry.expire() == []
    worker = registry.get("sim-1")
    assert worker.online is True
    assert worker.n_samples == 250
    assert worker.registration_count == 2


def test_model_compatibility_accepts_empty_expectation() -> None:
    assert model_compatibility({}, {}) == (True, None)
    assert model_compatibility({}, MODEL)[0] is False
    assert model_compatibility(MODEL, MODEL) == (True, None)
