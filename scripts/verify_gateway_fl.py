#!/usr/bin/env python
"""Real end-to-end demo: gateways as independent federated-learning clients.

This script turns three simulator gateways into FL clients (Stack 3), starts the
real control coordinator, runs one round with all three gateways, drops one
gateway, and runs a second round with the two survivors.  It checks:

* each gateway owns a distinct, disjoint partition of the historical training
  years and reports a usable number of real training windows;
* every gateway loads the retained global model, trains the real CNN-RNN on its
  own shard, evaluates locally, and uploads a real float32 update;
* the coordinator's sample-weighted FedAvg changes the global weights and
  registers a new model version;
* a dropped gateway is excluded and the round still completes with the rest.

Usage (project root, venv activated, mosquitto installed)::

    python scripts/verify_gateway_fl.py --gateways 3 --timeout 1800

Everything is written under a temporary directory; the committed registry and
the telemetry stores are never touched.
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
from simulator.fl_client import GatewayFLFleet  # noqa: E402
from simulator.fl_storage import FLStorageComponent  # noqa: E402


def _wait_for_log(path: Path, needle: str, timeout: float, process: Any) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        if process.poll() is not None:
            raise SystemExit(f"process exited early; {path} tail:\n{text[-4000:]}")
        if needle in text:
            return
        time.sleep(0.2)
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    raise SystemExit(f"timed out waiting for {needle!r} in {path}:\n{text[-4000:]}")


class Sniffer:
    """Read-only MQTT observer for registrations, states, and summaries."""

    def __init__(self, port: int, base_topic: str = "aq") -> None:
        self.base_topic = base_topic
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self.client = create_client(
            f"verify-gw-{uuid.uuid4().hex[:6]}", "127.0.0.1", port, keepalive=10
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect("127.0.0.1", port, 10)
        self.client.loop_start()
        if not self._ready.wait(5):
            raise SystemExit("MQTT sniffer did not connect")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        del userdata, flags, reason_code, properties
        client.subscribe([(f"{self.base_topic}/#", 1)])
        self._ready.set()

    def _on_message(self, client, userdata, message):
        del client, userdata
        try:
            payload = loads(message.payload)
        except (TypeError, ValueError):
            return
        with self._lock:
            self.messages.append({"topic": message.topic, "payload": payload})

    def registrations(self) -> set[str]:
        with self._lock:
            return {
                item["payload"].get("worker_id")
                for item in self.messages
                if item["topic"].endswith("/register")
                and item["payload"].get("message_type") == "worker_register"
                and item["payload"].get("state") != "offline"
            }

    def offline(self, worker_id: str) -> bool:
        with self._lock:
            return any(
                item["topic"].endswith(f"/{worker_id}/state")
                and item["payload"].get("message_type") == "worker_state"
                and item["payload"].get("state") == "offline"
                for item in self.messages
            )

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            items = {
                int(item["payload"]["round"]): item["payload"]
                for item in self.messages
                if item["topic"].endswith("/summary")
                and item["payload"].get("message_type") == "round_summary"
            }
        return [items[key] for key in sorted(items)]

    def control(self, message: dict[str, Any]) -> None:
        publish_json(
            self.client, f"{self.base_topic}/fl/control", message, qos=1, retain=False
        ).wait_for_publish(timeout=5)

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()


def _latest(registry: Path) -> tuple[str, np.ndarray]:
    record = json.loads((registry / "latest.json").read_text(encoding="utf-8"))
    version = str(record["model_version"])
    weights = np.load(registry / f"global_{version}.npy", allow_pickle=False)
    return version, weights


def _start_session(
    sniffer: Sniffer,
    *,
    rounds: int,
    min_workers: int,
    max_workers: int,
    window_hours: int,
    deadline_sec: float,
) -> None:
    sniffer.control(
        build_control(
            "start_session",
            config={
                "mode": "fixed",
                "rounds": rounds,
                "min_workers": min_workers,
                "max_workers": max_workers,
                "local_epochs": 1,
                "deadline_sec": deadline_sec,
                "selection_strategy": "all",
                "aggregation_method": "fedavg",
                "window_hours": window_hours,
                "learning_rate": 0.001,
                "simulation_workers": 0,
                "launch_workers": False,
                "worker_role": "training",
            },
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateways", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--window-hours", type=int, default=3)
    parser.add_argument("--local-epochs", type=int, default=1)
    args = parser.parse_args()
    if args.gateways < 2:
        raise SystemExit("--gateways must be at least 2")
    if args.gateways != 3:
        print("note: the acceptance demo uses exactly 3 gateways")

    port = free_port()
    tmp = Path(tempfile.mkdtemp(prefix="airfed-gateway-fl-"))
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
    model = {
        **source.get("model", {}),
        "batch_size": 64,
        "conv_filters": 8,
        "rnn_units": 8,
        "dropout": 0.1,
        "max_epochs": 1,
        "patience": 1,
    }
    config["model"] = model
    config["federated"] = {
        **source.get("federated", {}),
        "deadline_sec": 600,
        "min_clients": args.gateways,
        "rounds": 1,
        "local_epochs": args.local_epochs,
    }
    config["window_hours"] = args.window_hours
    config_path = tmp / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    gateway_ids = [f"gateway-{index + 1:02d}" for index in range(args.gateways)]
    print(f"runtime: {tmp}")
    print(f"broker:  127.0.0.1:{port}")
    print(f"gateways: {', '.join(gateway_ids)}")

    broker = start_broker(tmp, port)
    sniffer = Sniffer(port)
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
            str(args.timeout + 120),
        ],
        cwd=ROOT,
        stdout=coordinator_log,
        stderr=subprocess.STDOUT,
    )

    fleet = GatewayFLFleet(config_path=str(config_path), gateway_count=args.gateways)
    storage: dict[str, FLStorageComponent] = {}
    try:
        print("waiting for coordinator (TensorFlow import)…")
        _wait_for_log(tmp / "coordinator.log", "control mode ready", 600, coordinator)
        registry = tmp / "registry"
        initial_version, initial_weights = _latest(registry)
        print(f"initial model: {initial_version} ({initial_weights.size} params)")

        for gateway_id in gateway_ids:
            storage[gateway_id] = FLStorageComponent(
                gateway_id, root=tmp / "fl_gateways"
            )
            fleet.start(
                gateway_id,
                fl_storage=storage[gateway_id],
                host="127.0.0.1",
                port=port,
                window_hours=args.window_hours,
            )

        worker_for = {
            gateway_id: fleet.client(gateway_id).worker_id
            for gateway_id in gateway_ids
        }
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if len(sniffer.registrations()) >= len(gateway_ids):
                break
            time.sleep(0.25)
        registered = sniffer.registrations()
        print(f"registered FL clients: {sorted(registered)}")
        missing = set(worker_for.values()) - registered
        if missing:
            raise SystemExit(f"gateway FL clients did not register: {sorted(missing)}")

        partitions: dict[str, Any] = {}
        for gateway_id in gateway_ids:
            client = fleet.client(gateway_id)
            stats = client.stats()
            partition = stats.get("partition") or {}
            samples = int(partition.get("n_samples") or 0)
            if samples <= 0:
                raise SystemExit(f"{gateway_id} has no training windows")
            partitions[gateway_id] = {
                "worker_id": client.worker_id,
                "gateway_index": client.gateway_index,
                "gateway_count": client.gateway_count,
                "years": partition.get("years"),
                "shard_indices": partition.get("shard_indices"),
                "n_samples": samples,
                "n_val": partition.get("n_val"),
                "source_rows": partition.get("source_rows"),
            }
            print(
                f"{gateway_id} -> {client.worker_id}: index={client.gateway_index}/"
                f"{client.gateway_count} years={partition.get('years')} "
                f"shards={partition.get('shard_indices')} "
                f"train={samples} val={partition.get('n_val')} "
                f"source_rows={partition.get('source_rows')}"
            )

        seen: set[tuple[int, int]] = set()
        for item in partitions.values():
            for shard in item["shard_indices"] or []:
                key = (int(item["years"][0]), int(shard))
                if key in seen:
                    raise SystemExit(f"partition overlap on {key}")
                seen.add(key)
        if sum(int(item["n_samples"]) for item in partitions.values()) <= 0:
            raise SystemExit("no usable training windows across gateways")

        # ---- round 1: all gateways participate -------------------------
        print("round 1: starting session with all gateways…")
        _start_session(
            sniffer,
            rounds=1,
            min_workers=len(gateway_ids),
            max_workers=len(gateway_ids),
            window_hours=args.window_hours,
            deadline_sec=600,
        )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and len(sniffer.summaries()) < 1:
            time.sleep(0.5)
        summaries = sniffer.summaries()
        if not summaries:
            raise SystemExit("round 1 produced no summary")
        first = summaries[0]
        print("round 1 summary:", json.dumps(first, indent=2, default=str))
        if first["status"] != "completed" or not first["aggregated"]:
            raise SystemExit(f"round 1 did not complete: {first['status']}")
        expected_workers = set(worker_for.values())
        if set(first["accepted"]) != expected_workers:
            raise SystemExit(
                f"round 1 accepted {first['accepted']}, expected {sorted(expected_workers)}"
            )
        round1_version, round1_weights = _latest(registry)
        if round1_version == initial_version:
            raise SystemExit("round 1 did not register a new model version")
        if np.array_equal(initial_weights, round1_weights):
            raise SystemExit("round 1 left the global weights unchanged")

        # ---- drop one gateway, round 2 with the survivors --------------
        dropped = gateway_ids[-1]
        dropped_worker = worker_for[dropped]
        print(f"disconnecting {dropped} ({dropped_worker}) before round 2…")
        fleet.stop(dropped)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not sniffer.offline(dropped_worker):
            time.sleep(0.25)
        if not sniffer.offline(dropped_worker):
            print("warning: no offline heartbeat observed; relying on registry state")

        survivors = sorted(set(worker_for) - {dropped})
        survivor_workers = {worker_for[gateway_id] for gateway_id in survivors}
        print(f"round 2: starting session with {sorted(survivor_workers)}…")
        _start_session(
            sniffer,
            rounds=1,
            min_workers=len(survivors),
            max_workers=len(survivors),
            window_hours=args.window_hours,
            deadline_sec=600,
        )
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline and len(sniffer.summaries()) < 2:
            time.sleep(0.5)
        summaries = sniffer.summaries()
        if len(summaries) < 2:
            raise SystemExit("round 2 produced no summary")
        second = summaries[1]
        print("round 2 summary:", json.dumps(second, indent=2, default=str))
        if second["status"] != "completed" or not second["aggregated"]:
            raise SystemExit(f"round 2 did not complete: {second['status']}")
        if set(second["accepted"]) != survivor_workers:
            raise SystemExit(
                f"round 2 accepted {second['accepted']}, expected "
                f"{sorted(survivor_workers)}"
            )
        if dropped_worker in second["selected"]:
            raise SystemExit(f"dropped gateway {dropped_worker} was still selected")
        round2_version, round2_weights = _latest(registry)
        if round2_version == round1_version:
            raise SystemExit("round 2 did not register a new model version")
        if np.array_equal(round1_weights, round2_weights):
            raise SystemExit("round 2 left the global weights unchanged")

        evidence = {
            "partitions": partitions,
            "initial_model": initial_version,
            "round1": {
                "model_version": round1_version,
                "selected": first["selected"],
                "accepted": first["accepted"],
                "contributions": first.get("contributions", []),
                "weights_changed": not np.array_equal(initial_weights, round1_weights),
                "params": int(round1_weights.size),
            },
            "dropped_gateway": {"gateway_id": dropped, "worker_id": dropped_worker},
            "round2": {
                "model_version": round2_version,
                "selected": second["selected"],
                "accepted": second["accepted"],
                "contributions": second.get("contributions", []),
                "weights_changed": not np.array_equal(round1_weights, round2_weights),
            },
            "registry": str(registry),
        }
        (tmp / "evidence.json").write_text(
            json.dumps(evidence, indent=2, default=str), encoding="utf-8"
        )
        print("EVIDENCE:", json.dumps(evidence, indent=2, default=str))
        print(
            "OK: 3 real gateway updates were aggregated, then a dropout round "
            "completed with the remaining gateways."
        )
        return 0
    finally:
        try:
            fleet.stop_all(timeout=20)
        except Exception:
            pass
        if coordinator.poll() is None:
            coordinator.terminate()
            try:
                coordinator.wait(timeout=20)
            except Exception:
                coordinator.kill()
        coordinator_log.close()
        sniffer.stop()
        broker.terminate()
        try:
            broker.wait(timeout=5)
        except Exception:
            broker.kill()


if __name__ == "__main__":
    raise SystemExit(main())
