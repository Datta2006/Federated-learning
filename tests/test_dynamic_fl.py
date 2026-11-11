"""Real-broker integration tests for the dashboard-controlled dynamic coordinator.

These tests exercise the actual MQTT lifecycle: workers register themselves,
the coordinator waits for a minimum participation count, freezes selection per
round, aggregates sample-weighted dummy weights, and publishes retained
progress/summary messages.  Dummy weights avoid importing TensorFlow, while
still exercising the real upload/chunk/validation/aggregation path.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from common.config import PROJECT_ROOT
from common.mqtt_utils import create_client, loads, publish_json
from common.worker_protocol import build_control
from tests.broker_utils import free_port, start_broker

pytest.importorskip("paho.mqtt.client")

NODES = {"node1": 2010, "node2": 2011, "node3": 2012, "node4": 2013, "node5": 2014}


def _write_config(tmp_path: Path, port: int) -> Path:
    config = {
        "schema_version": 1,
        "nodes": dict(NODES),
        "mqtt": {
            "base_topic": "aq",
            "host": "127.0.0.1",
            "port": port,
            "qos": 1,
            "keepalive": 10,
            "heartbeat_sec": 1,
            "chunk_size": 2048,
        },
        "paths": {"model_dir": str(tmp_path / "registry")},
        "model": {
            "batch_size": 64,
            "conv_filters": 64,
            "dropout": 0.2,
            "kernel_size": 2,
            "learning_rate": 0.001,
            "max_epochs": 1,
            "patience": 1,
            "pool_size": 1,
            "rnn_units": 64,
        },
        "federated": {
            "deadline_sec": 10,
            "inference_only_nodes": ["node5"],
            "local_epochs": 1,
            "min_clients": 1,
            "rounds": 1,
            "training_nodes": ["node1", "node2", "node3", "node4"],
        },
        "seed": 42,
        "seeds": [42],
        "train_fraction": 0.8,
        "val_fraction_of_train": 0.1,
        "features": ["pm25", "temp", "rh"],
        "dataset_path": "data/beijing_pm25.csv",
        "scaler": {"feature_min": [0, 0, 0], "feature_max": [1, 1, 1]},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _spawn(
    tmp_path: Path,
    config_path: Path,
    port: int,
    name: str,
    module: str,
    arguments: list[str],
) -> tuple[subprocess.Popen, Any]:
    handle = (tmp_path / f"{name}.log").open("wb")
    command = [
        sys.executable,
        "-m",
        module,
        "--config",
        str(config_path),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        *arguments,
    ]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return process, handle


def _stop(process: subprocess.Popen, handle: Any) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if not handle.closed:
        handle.close()


def _wait_for_log(path: Path, needle: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and needle in path.read_text(
            encoding="utf-8", errors="replace"
        ):
            return
        time.sleep(0.05)
    text = (
        path.read_text(encoding="utf-8", errors="replace")
        if path.exists()
        else "<missing>"
    )
    raise AssertionError(f"{needle!r} not found in {path}:\n{text}")


class _Sniffer:
    def __init__(self, port: int, base_topic: str = "aq") -> None:
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._connected = threading.Event()
        self.base_topic = base_topic
        self.client = create_client(
            f"sniff-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port, 10)
        self.client.loop_start()
        assert self._connected.wait(timeout=5.0)

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        del userdata, flags, reason_code, properties
        client.subscribe([(f"{self.base_topic}/#", 1)])
        self._connected.set()

    def _on_message(self, client, userdata, message):
        del client, userdata
        try:
            payload = loads(message.payload)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.messages.append(
                {"topic": message.topic, "payload": payload, "retain": message.retain}
            )

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            found = [
                message["payload"]
                for message in self.messages
                if message["topic"].endswith("/summary")
                and message["payload"].get("message_type") == "round_summary"
            ]
        unique: dict[int, dict[str, Any]] = {}
        for summary in found:
            unique[int(summary["round"])] = summary
        return [unique[key] for key in sorted(unique)]

    def session_state(self) -> dict[str, Any] | None:
        with self._lock:
            states = [
                message["payload"]
                for message in self.messages
                if message["topic"].endswith("/fl/session")
                and message["payload"].get("message_type") == "session_state"
            ]
        return states[-1] if states else None

    def wait_for_session_state(self, state: str, timeout: float = 20.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snapshot = self.session_state()
            if snapshot and snapshot.get("state") == state:
                return snapshot
            time.sleep(0.1)
        return self.session_state()

    def control(self, message: dict[str, Any]) -> None:
        publish_json(
            self.client,
            f"{self.base_topic}/fl/control",
            message,
            qos=1,
            retain=False,
        ).wait_for_publish(timeout=5.0)

    def wait_for_summaries(self, count: int, timeout: float = 90.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            summaries = self.summaries()
            if len(summaries) >= count:
                return summaries
            time.sleep(0.2)
        return self.summaries()

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def _session_config(**overrides) -> dict[str, Any]:
    config = {
        "mode": "fixed",
        "rounds": 1,
        "min_workers": 1,
        "max_workers": None,
        "local_epochs": 1,
        "deadline_sec": 15,
        "selection_strategy": "all",
        "aggregation_method": "fedavg",
        "window_hours": 24,
        "learning_rate": 0.001,
        "simulation_workers": 0,
        "launch_workers": False,
        "worker_role": "training",
    }
    config.update(overrides)
    return config


def _run_dynamic(tmp_path: Path, workers: list[tuple[str, list[str]]], config: dict[str, Any], expected: int):
    port = free_port()
    broker = start_broker(tmp_path, port)
    config_path = _write_config(tmp_path, port)
    sniffer = _Sniffer(port)
    processes: list[tuple[subprocess.Popen, Any]] = []
    coordinator = None
    coordinator_handle = None
    try:
        coordinator, coordinator_handle = _spawn(
            tmp_path,
            config_path,
            port,
            "coordinator",
            "server.fl_coordinator",
            [
                "--control",
                "--dummy",
                "--dummy-count",
                "16",
                "--run-seconds",
                "90",
            ],
        )
        _wait_for_log(tmp_path / "coordinator.log", "control mode ready", timeout=20)

        for name, arguments in workers:
            process, handle = _spawn(
                tmp_path,
                config_path,
                port,
                name,
                "node.fl_node",
                ["--node-id", name, *arguments, "--dynamic", "--run-seconds", "80"],
            )
            processes.append((process, handle))

        time.sleep(1.5)
        sniffer.control(build_control("start_session", config=config))
        summaries = sniffer.wait_for_summaries(expected, timeout=80)
        return summaries, tmp_path
    finally:
        for process, handle in processes:
            _stop(process, handle)
        if coordinator is not None:
            _stop(coordinator, coordinator_handle)
        # The coordinator may have marked the stop; give workers a beat.
        sniffer.stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()


def test_dynamic_four_worker_session_aggregates_and_excludes_inference(
    tmp_path: Path,
) -> None:
    workers = [
        (
            f"sim-{index}",
            [
                "--dummy",
                "--dummy-count",
                "16",
                "--dummy-value",
                str(float(index)),
                "--dummy-samples",
                str(100 * index),
            ],
        )
        for index in range(1, 5)
    ]
    workers.append(
        (
            "infer-1",
            ["--dummy", "--dummy-count", "16", "--inference-only"],
        )
    )

    summaries, path = _run_dynamic(
        tmp_path,
        workers,
        _session_config(rounds=2, min_workers=4),
        expected=2,
    )

    assert len(summaries) >= 2, summaries
    for summary in summaries[:2]:
        assert summary["status"] == "completed"
        assert summary["aggregated"] is True
        assert summary["single_client"] is False
        assert sorted(summary["selected"]) == ["sim-1", "sim-2", "sim-3", "sim-4"]
        assert "infer-1" not in summary["selected"]
        assert sorted(summary["accepted"]) == ["sim-1", "sim-2", "sim-3", "sim-4"]
        assert summary["rejected"] == {}

    # Sample-weighted FedAvg: (1*100 + 2*200 + 3*300 + 4*400) / 1000 = 3.0
    import numpy as np

    weights = np.load(path / "registry" / "global_v0002.npy")
    np.testing.assert_allclose(weights, np.full(16, 3.0, dtype=np.float32))

    rounds = list(
        __import__("csv").DictReader(
            (path / "registry" / "rounds.csv").open(encoding="utf-8", newline="")
        )
    )
    assert [row["model_version"] for row in rounds[:2]] == ["v0001", "v0002"]
    assert all(row["received"] == "4" for row in rounds[:2])
    latest = json.loads((path / "registry" / "latest.json").read_text(encoding="utf-8"))
    assert latest["model_version"] == "v0002"


def test_dynamic_single_worker_round_is_marked_single_client(tmp_path: Path) -> None:
    summaries, _path = _run_dynamic(
        tmp_path,
        [
            (
                "solo-1",
                [
                    "--dummy",
                    "--dummy-count",
                    "16",
                    "--dummy-value",
                    "7.0",
                    "--dummy-samples",
                    "100",
                ],
            )
        ],
        _session_config(rounds=1, min_workers=1),
        expected=1,
    )

    assert len(summaries) >= 1, summaries
    summary = summaries[0]
    assert summary["status"] == "completed"
    assert summary["single_client"] is True
    assert summary["aggregated"] is True
    assert summary["selected"] == ["solo-1"]
    assert summary["accepted"] == ["solo-1"]


def test_dynamic_ten_worker_single_round_aggregates_all_updates(
    tmp_path: Path,
) -> None:
    """A 10-worker live session exercises dynamic selection beyond four nodes."""
    workers = [
        (
            f"sim-{index}",
            [
                "--dummy",
                "--dummy-count",
                "16",
                "--dummy-value",
                str(float(index)),
                "--dummy-samples",
                str(100 * index),
            ],
        )
        for index in range(1, 11)
    ]

    summaries, path = _run_dynamic(
        tmp_path,
        workers,
        _session_config(rounds=1, min_workers=10),
        expected=1,
    )

    assert len(summaries) >= 1, summaries
    summary = summaries[0]
    assert summary["status"] == "completed"
    assert summary["aggregated"] is True
    assert summary["single_client"] is False
    assert sorted(summary["selected"]) == sorted(
        f"sim-{index}" for index in range(1, 11)
    )
    assert sorted(summary["accepted"]) == sorted(
        f"sim-{index}" for index in range(1, 11)
    )
    assert summary["rejected"] == {}

    # Sample-weighted FedAvg over values 1..10 and samples 100..1000:
    # sum(i * 100i) / sum(100i) = sum(i^2) / sum(i) = 385 / 55 = 7.0
    import numpy as np

    weights = np.load(path / "registry" / "global_v0001.npy")
    np.testing.assert_allclose(weights, np.full(16, 7.0, dtype=np.float32))


def test_no_worker_session_waits_then_stops_without_aggregation(
    tmp_path: Path,
) -> None:
    """With no workers the session must wait (not fabricate rounds) until stopped."""
    port = free_port()
    broker = start_broker(tmp_path, port)
    config_path = _write_config(tmp_path, port)
    sniffer = _Sniffer(port)
    coordinator = None
    coordinator_handle = None
    try:
        coordinator, coordinator_handle = _spawn(
            tmp_path,
            config_path,
            port,
            "coordinator",
            "server.fl_coordinator",
            [
                "--control",
                "--dummy",
                "--dummy-count",
                "16",
                "--run-seconds",
                "60",
            ],
        )
        _wait_for_log(tmp_path / "coordinator.log", "control mode ready", timeout=20)

        sniffer.control(
            build_control(
                "start_session",
                config=_session_config(rounds=1, min_workers=2),
            )
        )
        waiting = sniffer.wait_for_session_state("waiting", timeout=15)
        assert waiting is not None, "the coordinator must publish a waiting state"
        assert waiting["state"] == "waiting"
        assert waiting["completed_rounds"] == 0
        assert waiting["config"]["min_workers"] == 2

        # Give the coordinator time to (incorrectly) run a round if it were to.
        time.sleep(2.0)
        assert sniffer.summaries() == [], "no round may run without workers"
        assert sniffer.session_state()["state"] == "waiting"

        sniffer.control(build_control("stop_session"))
        stopped = sniffer.wait_for_session_state("stopped", timeout=15)
        assert stopped is not None
        assert stopped["state"] == "stopped"
        assert stopped["completed_rounds"] == 0
        assert sniffer.summaries() == []
    finally:
        if coordinator is not None:
            _stop(coordinator, coordinator_handle)
        sniffer.stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
