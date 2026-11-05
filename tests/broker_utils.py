"""Shared throwaway-broker helpers for MQTT integration tests."""

from __future__ import annotations

import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path

import pytest


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=0.2)):
                return
        except OSError:
            time.sleep(0.05)
    raise AssertionError(f"broker did not listen on port {port}")


def start_broker(tmp_path: Path, port: int) -> subprocess.Popen:
    import shutil

    mosquitto = shutil.which("mosquitto")
    if mosquitto is None:
        pytest.skip("mosquitto binary is not installed")
    config = tmp_path / "mosquitto.conf"
    config.write_text(
        f"listener {port} 127.0.0.1\n"
        "allow_anonymous true\n"
        "persistence false\n"
        "log_dest none\n",
        encoding="utf-8",
    )
    process = subprocess.Popen(
        [mosquitto, "-c", str(config)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for_port(port)
    return process
