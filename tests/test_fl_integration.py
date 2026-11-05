"""Real-broker Stage 4 integration tests for complete and interrupted rounds.

The first test runs a three-node dummy round and checks the hand-computed
weighted FedAvg result, the registry, ``rounds.csv``, and that no payload on
any topic carries a raw-reading field.  The second starts four nodes with
``min_clients=3``, kills node4 after the round begins, and checks that the round
still completes and registers a model from the three survivors.
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

import numpy as np
import pytest

from common.config import PROJECT_ROOT
from common.mqtt_utils import create_client, loads
from tests.broker_utils import free_port, start_broker

pytest.importorskip("paho.mqtt.client")

FORBIDDEN_KEYS = {
    "pm25",
    "pm2.5",
    "temp",
    "temperature",
    "rh",
    "humidity",
    "dewpoint",
    "dew_point",
    "reading",
    "readings",
    "sensor_values",
}

ALL_NODES = {"node1": 2010, "node2": 2011, "node3": 2012, "node4": 2013, "node5": 2014}


def _write_config(tmp_path: Path, port: int) -> Path:
    config = {
        "schema_version": 1,
        "nodes": dict(ALL_NODES),
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
            "min_clients": 3,
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
    """Collect every JSON message published under ``aq/#``."""

    def __init__(self, port: int) -> None:
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._connected = threading.Event()
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
        client.subscribe([("aq/#", 1)])
        self._connected.set()

    def _on_message(self, client, userdata, message):
        del client, userdata
        try:
            payload = loads(message.payload)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.messages.append({"topic": message.topic, "payload": payload})

    def stop(self) -> list[dict[str, Any]]:
        self.client.disconnect()
        self.client.loop_stop()
        with self._lock:
            return list(self.messages)


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def _read_rounds(tmp_path: Path) -> list[dict[str, str]]:
    import csv

    with (tmp_path / "registry" / "rounds.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        return list(csv.DictReader(handle))


def test_three_node_round_aggregates_by_sample_count_and_publishes_nothing_raw(
    tmp_path: Path,
) -> None:
    port = free_port()
    broker = start_broker(tmp_path, port)
    config_path = _write_config(tmp_path, port)
    sniffer = _Sniffer(port)
    nodes: list[tuple[subprocess.Popen, Any]] = []
    server_handle = None
    try:
        # Unequal sample counts: (100*1 + 200*4 + 300*7) / 600 = 5.0
        for node_id, value, samples in (
            ("node1", 1.0, 100),
            ("node2", 4.0, 200),
            ("node3", 7.0, 300),
        ):
            process, handle = _spawn(
                tmp_path,
                config_path,
                port,
                node_id,
                "node.fl_node",
                [
                    "--node-id",
                    node_id,
                    "--dummy",
                    "--dummy-count",
                    "16",
                    "--dummy-value",
                    str(value),
                    "--dummy-samples",
                    str(samples),
                    "--run-seconds",
                    "40",
                ],
            )
            nodes.append((process, handle))

        time.sleep(0.8)
        server, server_handle = _spawn(
            tmp_path,
            config_path,
            port,
            "server",
            "server.fl_coordinator",
            [
                "--rounds",
                "1",
                "--min-clients",
                "3",
                "--startup-wait-sec",
                "3",
                "--client-wait-sec",
                "10",
                "--dummy",
                "--dummy-count",
                "16",
            ],
        )
        assert server.wait(timeout=45) == 0

        for process, handle in nodes:
            _stop(process, handle)
        time.sleep(0.3)
        messages = sniffer.stop()

        rounds = _read_rounds(tmp_path)
        assert len(rounds) == 1
        assert rounds[0]["received"] == "3"
        assert rounds[0]["dropped_nodes"] == ""
        assert rounds[0]["model_version"] == "v0001"
        assert rounds[0]["evaluated_version"] == "v0000"
        assert float(rounds[0]["weighted_val_loss"]) == pytest.approx(5.0)

        weights = np.load(tmp_path / "registry" / "global_v0001.npy")
        np.testing.assert_allclose(weights, np.full(16, 5.0, dtype=np.float32))
        latest = json.loads(
            (tmp_path / "registry" / "latest.json").read_text(encoding="utf-8")
        )
        assert latest["model_version"] == "v0001"
        assert latest["n_samples"] == 600
        # v0001 has not been evaluated yet; the score belongs to v0000.
        assert latest["weighted_val_loss"] is None
        best = json.loads(
            (tmp_path / "registry" / "best.json").read_text(encoding="utf-8")
        )
        assert best["model_version"] == "v0000"
        assert best["weighted_val_loss"] == pytest.approx(5.0)

        for node_id in ("node1", "node2", "node3"):
            log = (tmp_path / f"{node_id}.log").read_text(
                encoding="utf-8", errors="replace"
            )
            assert "ack=accepted" in log
            assert (
                f"n_samples={100 if node_id == 'node1' else 200 if node_id == 'node2' else 300}"
                in log
            )

        assert messages, "no messages were captured"
        for message in messages:
            keys = {str(key).lower() for key in _walk_keys(message["payload"])}
            leaked = keys.intersection(FORBIDDEN_KEYS)
            assert not leaked, f"raw reading field {leaked} on {message['topic']}"
    finally:
        if server_handle is not None:
            server_handle.close()
        for process, handle in nodes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if not handle.closed:
                handle.close()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()


def test_round_completes_when_a_selected_node_is_killed_mid_round(
    tmp_path: Path,
) -> None:
    port = free_port()
    broker = start_broker(tmp_path, port)
    config_path = _write_config(tmp_path, port)
    nodes: list[tuple[str, subprocess.Popen, Any]] = []
    server_handle = None
    try:
        for node_id, value in (
            ("node1", 1.0),
            ("node2", 2.0),
            ("node3", 3.0),
            ("node4", 4.0),
        ):
            arguments = [
                "--node-id",
                node_id,
                "--dummy",
                "--dummy-count",
                "16",
                "--dummy-value",
                str(value),
                "--dummy-samples",
                "100",
                "--run-seconds",
                "40",
            ]
            if node_id == "node4":
                arguments.extend(["--upload-delay", "20"])
            process, handle = _spawn(
                tmp_path,
                config_path,
                port,
                node_id,
                "node.fl_node",
                arguments,
            )
            nodes.append((node_id, process, handle))

        inference_node, inference_handle = _spawn(
            tmp_path,
            config_path,
            port,
            "node5",
            "node.fl_node",
            [
                "--node-id",
                "node5",
                "--inference-only",
                "--seed",
                "42",
                "--run-seconds",
                "40",
            ],
        )
        nodes.append(("node5", inference_node, inference_handle))

        time.sleep(0.8)
        server, server_handle = _spawn(
            tmp_path,
            config_path,
            port,
            "server",
            "server.fl_coordinator",
            [
                "--rounds",
                "1",
                "--min-clients",
                "3",
                "--deadline-sec",
                "4",
                "--startup-wait-sec",
                "3",
                "--client-wait-sec",
                "10",
                "--dummy",
                "--dummy-count",
                "16",
            ],
        )
        _wait_for_log(tmp_path / "server.log", "round 1 started")
        node4 = next(process for node_id, process, _ in nodes if node_id == "node4")
        node4.kill()
        node4.wait(timeout=5)

        assert server.wait(timeout=45) == 0
        for node_id, process, handle in nodes:
            if node_id != "node4":
                _stop(process, handle)
            else:
                handle.close()

        inference_log = (tmp_path / "node5.log").read_text(
            encoding="utf-8", errors="replace"
        )
        assert "inference_only=True" in inference_log
        assert "uploaded round" not in inference_log

        rounds = _read_rounds(tmp_path)
        assert len(rounds) == 1
        assert rounds[0]["received"] == "3"
        assert "node4" in rounds[0]["dropped_nodes"]
        assert rounds[0]["model_version"] == "v0001"
        assert rounds[0]["evaluated_version"] == "v0000"

        # (1 + 2 + 3) / 3 = 2.0
        weights = np.load(tmp_path / "registry" / "global_v0001.npy")
        np.testing.assert_allclose(weights, np.full(16, 2.0, dtype=np.float32))
    finally:
        if server_handle is not None:
            server_handle.close()
        for node_id, process, handle in nodes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            if not handle.closed:
                handle.close()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
