"""Pytest-aware throwaway-broker helpers for MQTT integration tests."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from common.broker import free_port, wait_for_port
from common.broker import start_broker as _start_broker

__all__ = ["free_port", "start_broker", "wait_for_port"]


def start_broker(tmp_path: Path, port: int) -> subprocess.Popen:
    """Start a private broker, or skip the test when Mosquitto is absent."""
    if shutil.which("mosquitto") is None:
        pytest.skip("mosquitto binary is not installed")
    return _start_broker(tmp_path, port)
