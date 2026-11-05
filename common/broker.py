"""Throwaway local Mosquitto broker helpers for experiments.

Integration tests and the Stage 4 experiment both need a private loopback broker.
This module lives in ``common`` so production experiment code does not import
from the test package; ``tests/broker_utils.py`` is a thin pytest-aware wrapper.
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from contextlib import closing
from pathlib import Path


class BrokerError(RuntimeError):
    """Raised when no local broker binary is available or it never listens."""


def free_port() -> int:
    """Return an unused TCP port on the loopback interface."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_port(port: int, timeout: float = 10.0) -> None:
    """Block until *port* accepts a loopback connection."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with closing(socket.create_connection(("127.0.0.1", port), timeout=0.2)):
                return
        except OSError:
            time.sleep(0.05)
    raise BrokerError(f"broker did not listen on port {port}")


def start_broker(tmp_path: Path, port: int) -> subprocess.Popen:
    """Start an anonymous, non-persistent Mosquitto listener on *port*."""
    mosquitto = shutil.which("mosquitto")
    if mosquitto is None:
        raise BrokerError("mosquitto binary is not installed")
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
