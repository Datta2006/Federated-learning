"""Real-broker integration tests for Stage 3 sender -> receiver -> ack."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from common.config import PROJECT_ROOT
from common.mqtt_utils import create_client, loads, publish_json
from common.weight_transfer import (
    build_transfer_metadata,
    make_dummy_weights,
    round_ack_topic,
    round_update_meta_topic,
)
from tests.broker_utils import free_port, start_broker

pytest.importorskip("paho.mqtt.client")


def _stage3_config(tmp_path: Path, port: int) -> Path:
    config = {
        "schema_version": 1,
        "nodes": {"node1": 2010, "node5": 2014},
        "mqtt": {
            "base_topic": "aq",
            "host": "127.0.0.1",
            "port": port,
            "qos": 1,
            "keepalive": 10,
            "heartbeat_sec": 1,
            "chunk_size": 4096,
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
            "pool_size": 2,
            "rnn_units": 64,
        },
        "federated": {
            "deadline_sec": 30,
            "inference_only_nodes": ["node5"],
            "local_epochs": 1,
            "min_clients": 1,
            "rounds": 1,
            "training_nodes": ["node1"],
        },
        "seed": 42,
        "seeds": [42],
        "train_fraction": 0.8,
        "val_fraction_of_train": 0.1,
    }
    path = tmp_path / "stage3_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _read_until(path: Path, needle: str, timeout: float = 10.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if needle in text:
                return text
        time.sleep(0.05)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    raise AssertionError(f"{needle!r} not found in {path}:\n{text}")


def _start_receiver(
    config: Path,
    port: int,
    out_dir: Path,
    log_path: Path,
    *,
    missing_timeout: float = 2.0,
) -> subprocess.Popen:
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "server.weight_receiver",
                "--config",
                str(config),
                "--mode",
                "update",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--out-dir",
                str(out_dir),
                "--missing-timeout",
                str(missing_timeout),
                "--run-seconds",
                "30",
                "--verbose",
            ],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    _read_until(log_path, "subscribed")
    return process


def _run_sender(
    config: Path,
    port: int,
    *extra: str,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "node.weight_sender",
            "--config",
            str(config),
            "--mode",
            "update",
            "--node-id",
            "node1",
            "--round",
            "1",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--chunk-size",
            "2048",
            "--wait-ack",
            "--ack-timeout",
            "10",
            "--verbose",
            *extra,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )


def _stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _publish_unauthorised_update(port: int, metadata: dict, timeout: float = 10.0):
    """Publish node5 metadata directly and return the server's ack payload."""
    ack_topic = round_ack_topic("aq", 1, "node5")
    ack: dict = {}
    ack_received = threading.Event()
    subscribed = threading.Event()

    client = create_client(
        f"test-node5-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10
    )

    def on_connect(client, userdata, flags, reason_code, properties=None):
        del userdata, flags, reason_code, properties
        client.subscribe(ack_topic, qos=1)

    def on_subscribe(client, userdata, mid, reason_codes, properties=None):
        del client, userdata, mid, reason_codes, properties
        subscribed.set()

    def on_message(client, userdata, message):
        del client, userdata
        if message.topic != ack_topic:
            return
        ack.update(loads(message.payload))
        ack_received.set()

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect("127.0.0.1", port, 10)
    client.loop_start()
    try:
        assert subscribed.wait(timeout=5.0), "ack subscription was not confirmed"
        publish_json(
            client,
            round_update_meta_topic("aq", 1, "node5"),
            metadata,
            qos=1,
            retain=False,
        )
        assert ack_received.wait(timeout=timeout), "no ack received"
        return ack
    finally:
        client.disconnect()
        client.loop_stop()


def test_sender_receiver_ack_round_trip_over_a_real_broker(tmp_path):
    port = free_port()
    broker = start_broker(tmp_path, port)
    receiver = None
    try:
        config = _stage3_config(tmp_path, port)
        out_dir = tmp_path / "registry"
        receiver = _start_receiver(config, port, out_dir, tmp_path / "receiver.log")
        sender = _run_sender(
            config,
            port,
            "--dummy",
            "--dummy-count",
            "5000",
        )

        assert sender.returncode == 0, sender.stdout + sender.stderr
        assert "ack accepted" in sender.stdout
        assert "chunks=10" in sender.stdout
        assert "saved" in (tmp_path / "receiver.log").read_text(encoding="utf-8")

        weights = np.load(out_dir / "round_1_node1.npy")
        np.testing.assert_array_equal(weights, make_dummy_weights(5000, 42))
        receipt = json.loads(
            (out_dir / "round_1_node1.json").read_text(encoding="utf-8")
        )
        assert receipt["metadata"]["chunks"] == 10
        assert receipt["metadata"]["sha256"] == sender.stdout.split("sha256=")[1][:64]
    finally:
        _stop(receiver)
        _stop(broker)


def test_a_corrupted_chunk_is_rejected_and_nothing_is_saved(tmp_path):
    port = free_port()
    broker = start_broker(tmp_path, port)
    receiver = None
    try:
        config = _stage3_config(tmp_path, port)
        out_dir = tmp_path / "registry"
        receiver = _start_receiver(config, port, out_dir, tmp_path / "receiver.log")
        sender = _run_sender(
            config,
            port,
            "--dummy",
            "--dummy-count",
            "5000",
            "--corrupt-chunk",
            "1",
        )

        assert sender.returncode == 2, sender.stdout + sender.stderr
        assert "ack rejected" in sender.stdout
        assert "checksum" in sender.stdout
        assert "rejected" in (tmp_path / "receiver.log").read_text(encoding="utf-8")
        assert not (out_dir / "round_1_node1.npy").exists()
    finally:
        _stop(receiver)
        _stop(broker)


def test_an_inference_only_update_is_rejected_with_an_ack(tmp_path):
    port = free_port()
    broker = start_broker(tmp_path, port)
    receiver = None
    try:
        config = _stage3_config(tmp_path, port)
        out_dir = tmp_path / "registry"
        receiver = _start_receiver(config, port, out_dir, tmp_path / "receiver.log")

        metadata = build_transfer_metadata(
            make_dummy_weights(5000, 42),
            node_id="node5",
            model_version="dummy-v1",
            model_config={},
            kind="dummy",
            round_number=1,
            chunk_size=2048,
        )
        ack = _publish_unauthorised_update(port, metadata)

        assert ack["status"] == "rejected"
        assert "inference-only" in str(ack["reason"])
        assert not (out_dir / "round_1_node5.npy").exists()
    finally:
        _stop(receiver)
        _stop(broker)


def test_a_missing_chunk_times_out_and_is_rejected(tmp_path):
    port = free_port()
    broker = start_broker(tmp_path, port)
    receiver = None
    try:
        config = _stage3_config(tmp_path, port)
        out_dir = tmp_path / "registry"
        receiver = _start_receiver(
            config, port, out_dir, tmp_path / "receiver.log", missing_timeout=1.0
        )
        sender = _run_sender(
            config,
            port,
            "--dummy",
            "--dummy-count",
            "5000",
            "--drop-chunk",
            "1",
        )

        assert sender.returncode == 2, sender.stdout + sender.stderr
        assert "ack rejected" in sender.stdout
        assert "missing" in sender.stdout
        assert "missing" in (tmp_path / "receiver.log").read_text(encoding="utf-8")
        assert not (out_dir / "round_1_node1.npy").exists()
    finally:
        _stop(receiver)
        _stop(broker)
