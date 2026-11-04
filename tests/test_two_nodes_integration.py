"""Integration test: node1 and node2 retain independent status and LWT.

Starts a throwaway Mosquitto broker on a free localhost port, runs the real
node client twice, kills node1 with SIGKILL, and checks that node1's retained
status becomes ``offline reason=lwt`` while node2 stays online. It then kills
node2 and checks that both retained statuses are independently ``lwt``.

Skips when the mosquitto binary is not installed.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path

import pytest

paho = pytest.importorskip("paho.mqtt.client")
import paho.mqtt.client as mqtt

from common.config import PROJECT_ROOT

MOSQUITTO = shutil.which("mosquitto")
pytestmark = pytest.mark.skipif(
    MOSQUITTO is None, reason="mosquitto binary is not installed"
)


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=0.2)):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"broker did not listen on port {port}")


def _start_broker(tmp_path: Path, port: int) -> subprocess.Popen:
    config = tmp_path / "mosquitto.conf"
    config.write_text(
        f"listener {port} 127.0.0.1\n"
        "allow_anonymous true\n"
        "persistence false\n"
        "log_dest none\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [MOSQUITTO, "-c", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _wait_for_port(port)
    return process


def _node_config(tmp_path: Path, port: int) -> Path:
    config = {
        "schema_version": 1,
        "nodes": {"node1": 2010, "node2": 2011},
        "mqtt": {
            "base_topic": "aq",
            "host": "127.0.0.1",
            "port": port,
            "qos": 1,
            "keepalive": 2,
            "heartbeat_sec": 0.5,
        },
    }
    path = tmp_path / "node_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _start_node(config: Path, node_id: str, log_path: Path) -> subprocess.Popen:
    with log_path.open("wb") as log:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "node.node_client",
                "--config",
                str(config),
                "--node-id",
                node_id,
                "--interval",
                "0.5",
                "--keepalive",
                "2",
                "--verbose",
            ],
            cwd=PROJECT_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )


def _collect_retained(port: int, timeout: float = 1.5) -> dict[str, dict]:
    seen: dict[str, dict] = {}
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"retained-probe-{uuid.uuid4().hex[:8]}",
        protocol=mqtt.MQTTv311,
    )

    def on_message(client, userdata, message) -> None:
        del client, userdata
        if not message.retain:
            return
        try:
            payload = json.loads(message.payload)
        except ValueError:
            return
        node_id = message.topic.split("/")[1]
        seen[node_id] = payload

    def on_connect(client, userdata, flags, reason_code, properties=None) -> None:
        del userdata, flags, reason_code, properties
        client.subscribe("aq/+/status", qos=1)

    client.on_message = on_message
    client.on_connect = on_connect
    client.connect("127.0.0.1", port, keepalive=10)
    client.loop_start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.05)
    client.loop_stop()
    client.disconnect()
    return seen


def _wait_for_status(port: int, predicate, timeout: float = 12.0) -> dict[str, dict]:
    deadline = time.time() + timeout
    seen: dict[str, dict] = {}
    while time.time() < deadline:
        seen = _collect_retained(port)
        if predicate(seen):
            return seen
        time.sleep(0.2)
    return seen


def test_two_nodes_have_independent_retained_status_and_lwt(tmp_path):
    port = _free_port()
    broker = _start_broker(tmp_path, port)
    config = _node_config(tmp_path, port)
    node1 = node2 = None
    try:
        node1 = _start_node(config, "node1", tmp_path / "node1.log")
        node2 = _start_node(config, "node2", tmp_path / "node2.log")

        online = _wait_for_status(
            port,
            lambda seen: seen.get("node1", {}).get("state") == "online"
            and seen.get("node2", {}).get("state") == "online",
        )
        assert online["node1"]["node_id"] == "node1"
        assert online["node2"]["node_id"] == "node2"

        os.kill(node1.pid, signal.SIGKILL)
        node1.wait(timeout=5)

        after_lwt = _wait_for_status(
            port,
            lambda seen: seen.get("node1", {}).get("state") == "offline"
            and seen.get("node1", {}).get("reason") == "lwt"
            and seen.get("node2", {}).get("state") == "online",
        )
        assert after_lwt["node1"]["state"] == "offline"
        assert after_lwt["node1"]["reason"] == "lwt"
        assert after_lwt["node2"]["state"] == "online"

        os.kill(node2.pid, signal.SIGKILL)
        node2.wait(timeout=5)
        both_lwt = _wait_for_status(
            port,
            lambda seen: seen.get("node1", {}).get("reason") == "lwt"
            and seen.get("node2", {}).get("reason") == "lwt",
        )
        assert both_lwt["node1"]["state"] == "offline"
        assert both_lwt["node1"]["reason"] == "lwt"
        assert both_lwt["node2"]["state"] == "offline"
        assert both_lwt["node2"]["reason"] == "lwt"
    finally:
        for process in (node1, node2):
            if process is not None and process.poll() is None:
                process.kill()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except subprocess.TimeoutExpired:
            broker.kill()
