#!/usr/bin/env python
"""End-to-end real-Model smoke test for dynamic simulation workers.

Unlike the pytest dynamic tests (which use dummy weights so they run without
TensorFlow), this script starts real simulation workers on contiguous shards of
the training years, lets them train the actual CNN-RNN, and verifies that the
control coordinator aggregates the uploaded float32 weights.

Usage (from the project root, with .venv activated):

    python scripts/verify_real_training.py --workers 2 --rounds 1 --timeout 900

The model is deliberately small so the check finishes in a few minutes. It
writes everything under a temporary directory, never the committed registry.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.broker import free_port, start_broker  # noqa: E402
from common.mqtt_utils import create_client, loads, publish_json  # noqa: E402
from common.worker_protocol import build_control  # noqa: E402


def _wait_for_log(path: Path, needle: str, timeout: float, process) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            raise SystemExit(f"process exited early; {path} tail:\n{text[-4000:]}")
        if path.exists() and needle in path.read_text(encoding="utf-8", errors="replace"):
            return
        time.sleep(0.2)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    raise SystemExit(f"timed out waiting for {needle!r} in {path}:\n{text[-4000:]}")


class Sniffer:
    def __init__(self, port: int, base_topic: str = "aq") -> None:
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self.client = create_client(f"verify-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port, 10)
        self.client.loop_start()
        if not self._ready.wait(5):
            raise SystemExit("MQTT sniffer did not connect")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        del userdata, flags, reason_code, properties
        client.subscribe([("aq/#", 1)])
        self._ready.set()

    def _on_message(self, client, userdata, message):
        del client, userdata
        try:
            payload = loads(message.payload)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.messages.append({"topic": message.topic, "payload": payload})

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            items = {
                int(item["payload"]["round"]): item["payload"]
                for item in self.messages
                if item["topic"].endswith("/summary")
                and item["payload"].get("message_type") == "round_summary"
            }
        return [items[key] for key in sorted(items)]

    def registrations(self) -> int:
        with self._lock:
            return len(
                {
                    item["payload"].get("worker_id")
                    for item in self.messages
                    if item["topic"].endswith("/register")
                    and item["payload"].get("message_type") == "worker_register"
                }
            )

    def control(self, message: dict[str, Any]) -> None:
        publish_json(self.client, "aq/fl/control", message, qos=1, retain=False).wait_for_publish(timeout=5)

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--local-epochs", type=int, default=1)
    parser.add_argument("--window-hours", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    if args.workers < 1:
        raise SystemExit("--workers must be >= 1")

    port = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="airfed-real-smoke-"))
    source = json.loads((ROOT / "common" / "config.json").read_text(encoding="utf-8"))
    config = dict(source)
    config["paths"] = {**source.get("paths", {}), "model_dir": str(tmp / "registry")}
    config["mqtt"] = {
        **source.get("mqtt", {}),
        "host": "127.0.0.1",
        "port": port,
        "heartbeat_sec": 1,
        "qos": 1,
        "chunk_size": 4096,
    }
    config["model"] = {
        **source.get("model", {}),
        "batch_size": 64,
        "conv_filters": 8,
        "rnn_units": 8,
        "pool_size": 1,
        "kernel_size": 2,
        "max_epochs": 1,
        "patience": 1,
        "dropout": 0.1,
    }
    config["federated"] = {
        **source.get("federated", {}),
        "deadline_sec": 300,
        "min_clients": args.workers,
        "rounds": args.rounds,
        "local_epochs": args.local_epochs,
    }
    config["window_hours"] = args.window_hours
    config_path = tmp / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    print(f"runtime: {tmp}")
    print(f"broker: 127.0.0.1:{port}")
    broker = start_broker(tmp, port)
    sniffer = Sniffer(port)
    processes: list[tuple[str, Any, Any]] = []
    try:
        coordinator_log = (tmp / "coordinator.log").open("wb")
        coordinator = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "server.fl_coordinator",
                "--config",
                str(config_path),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--control",
                "--window-hours",
                str(args.window_hours),
                "--run-seconds",
                str(args.timeout + 60),
            ],
            cwd=ROOT,
            stdout=coordinator_log,
            stderr=subprocess.STDOUT,
        )
        processes.append(("coordinator", coordinator, coordinator_log))
        print("waiting for coordinator (TensorFlow import)…")
        _wait_for_log(tmp / "coordinator.log", "control mode ready", 300, coordinator)

        for index in range(args.workers):
            worker_id = f"real-{index + 1}"
            handle = (tmp / f"{worker_id}.log").open("wb")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "node.fl_node",
                    "--config",
                    str(config_path),
                    "--node-id",
                    worker_id,
                    "--dynamic",
                    "--simulation",
                    "--shard-index",
                    str(index),
                    "--shard-count",
                    str(args.workers),
                    "--window-hours",
                    str(args.window_hours),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--run-seconds",
                    str(args.timeout),
                ],
                cwd=ROOT,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
            processes.append((worker_id, process, handle))
            print(f"launched {worker_id} (TensorFlow import + shard prep)…")

        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            if sniffer.registrations() >= args.workers:
                break
            time.sleep(0.5)
        registered = sniffer.registrations()
        print(f"registered workers: {registered}")
        if registered < args.workers:
            raise SystemExit("workers did not all register in time")

        sniffer.control(
            build_control(
                "start_session",
                config={
                    "mode": "fixed",
                    "rounds": args.rounds,
                    "min_workers": args.workers,
                    "max_workers": args.workers,
                    "local_epochs": args.local_epochs,
                    "deadline_sec": 300,
                    "selection_strategy": "all",
                    "aggregation_method": "fedavg",
                    "window_hours": args.window_hours,
                    "learning_rate": 0.001,
                    "simulation_workers": 0,
                    "launch_workers": False,
                    "worker_role": "training",
                },
            )
        )
        print("session started; waiting for round summaries…")
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            summaries = sniffer.summaries()
            if len(summaries) >= args.rounds:
                break
            time.sleep(1.0)
        summaries = sniffer.summaries()
        if not summaries:
            raise SystemExit("no round summary was published")
        for summary in summaries:
            print(json.dumps(summary, indent=2, default=str))
        last = summaries[-1]
        if last["status"] != "completed" or not last["aggregated"]:
            raise SystemExit(f"round did not aggregate successfully: {last['status']}")
        if not last["accepted"]:
            raise SystemExit("no accepted updates")
        version = last["model_version"]
        weights_path = tmp / "registry" / f"global_{version}.npy"
        if not weights_path.exists():
            raise SystemExit(f"registered weights missing: {weights_path}")
        weights = np.load(weights_path)
        if not np.isfinite(weights).all():
            raise SystemExit("aggregated weights contain non-finite values")
        print(f"OK: {len(last['accepted'])} real update(s) aggregated into {version} "
              f"({weights.size} parameters, loss={last['weighted_val_loss']})")
        return 0
    finally:
        for name, process, handle in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()
            handle.close()
        sniffer.stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except Exception:
            broker.kill()


if __name__ == "__main__":
    raise SystemExit(main())
