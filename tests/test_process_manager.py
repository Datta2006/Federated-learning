"""Tests for the dashboard process manager lifecycle and safety guards."""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

import pytest

from dashboard.backend.process_manager import ProcessError, ProcessManager, port_open
from tests.broker_utils import free_port


def _manager(tmp_path: Path) -> ProcessManager:
    return ProcessManager(
        host="127.0.0.1",
        port=59999,
        base_topic="aq",
        python=sys.executable,
        runtime_dir=tmp_path / "runtime",
    )


def test_duplicate_launch_is_refused_and_stop_is_graceful(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    process = manager._launch(
        name="probe",
        kind="worker",
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
    )
    try:
        assert process.alive()
        with pytest.raises(ProcessError, match="already running"):
            manager._launch(
                name="probe",
                kind="worker",
                command=[sys.executable, "-c", "print('nope')"],
            )
        logs = manager.logs("probe")
        assert logs["running"] is True
        assert logs["lines"], "the launch banner should be captured"
        assert manager.stop("probe") is True
        assert manager.status_of("probe") is None
        assert not (tmp_path / "runtime" / "probe.pid").exists()
    finally:
        manager.stop_all()


def test_crash_is_reported_with_log_tail(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager._launch(
        name="crasher",
        kind="worker",
        command=[sys.executable, "-c", "print('boom'); raise SystemExit(3)"],
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = manager.status()
        if status["crashes"]:
            break
        time.sleep(0.05)
    status = manager.status()
    assert status["crashes"], "a fast exit must be reported"
    crash = status["crashes"][0]
    assert crash["name"] == "crasher"
    assert crash["exit_code"] == 3
    assert any("boom" in line for line in crash["log_tail"])


def test_workers_require_a_reachable_broker(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(ProcessError, match="broker is not reachable"):
        manager.start_workers(count=1, dummy=True)


def test_missing_log_is_an_error(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    with pytest.raises(ProcessError, match="no log"):
        manager.logs("ghost")
    assert port_open("127.0.0.1", 59999) is False


def test_status_shape_and_stop_all(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    first = manager._launch(
        name="sim-1",
        kind="worker",
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        role="training",
    )
    second = manager._launch(
        name="coordinator",
        kind="coordinator",
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
    )
    assert first.alive() and second.alive()
    status = manager.status()
    assert status["coordinator"]["name"] == "coordinator"
    assert [item["name"] for item in status["workers"]] == ["sim-1"]
    assert status["broker"]["reachable"] is False
    stopped = manager.stop_all()
    assert set(stopped) == {"sim-1", "coordinator"}
    assert manager.status()["processes"] == []


def test_real_broker_and_control_coordinator_lifecycle(tmp_path: Path) -> None:
    """The dashboard launcher starts a real broker + coordinator and stops both."""
    if shutil.which("mosquitto") is None:
        pytest.skip("mosquitto binary is not installed")

    port = free_port()
    manager = ProcessManager(
        host="127.0.0.1",
        port=port,
        runtime_dir=tmp_path / "runtime",
    )
    try:
        broker = manager.start_broker(wait_sec=8.0)
        assert broker["ok"] is True
        assert broker["owned"] is True
        assert port_open("127.0.0.1", port) is True

        launched = manager.start_coordinator(
            dummy=True,
            extra_args=[
                "--model-dir",
                str(tmp_path / "registry"),
                "--run-seconds",
                "60",
            ],
        )
        assert launched["process"]["running"] is True

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            lines = manager.logs("coordinator")["lines"]
            if any("control mode ready" in line for line in lines):
                break
            if not manager.status_of("coordinator")["running"]:
                pytest.fail("coordinator exited early:\n" + "\n".join(lines))
            time.sleep(0.1)
        else:
            pytest.fail("coordinator did not report readiness")

        status = manager.status()
        assert status["broker"]["reachable"] is True
        assert status["coordinator"]["running"] is True
        assert status["workers"] == []
        assert status["crashes"] == []

        duplicate = manager.start_coordinator(dummy=True)
        assert "already running" in duplicate["message"]
        assert manager.logs("coordinator")["running"] is True

        stopped = manager.stop_all()
        assert {"broker", "coordinator"} <= set(stopped)
        assert manager.status()["processes"] == []
        assert port_open("127.0.0.1", port) is False
    finally:
        manager.stop_all()
