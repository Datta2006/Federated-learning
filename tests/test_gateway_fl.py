"""Unit tests for Stack 3 gateway federated-learning clients.

These tests avoid TensorFlow and MQTT.  They cover the participant identity,
the disjoint dataset partitioning, the single-flight fleet lifecycle, and the
separation from gateway telemetry storage.  The real CNN-RNN round path is
exercised by ``scripts/verify_gateway_fl.py``.
"""

from __future__ import annotations

import itertools
import re
import threading
from typing import Any

import numpy as np
import pandas as pd

from common.simulation import (
    gateway_shard_allocations,
    prepare_gateway_partition,
    training_years,
)
from simulator.engine import NetworkSimulator
from simulator.fl_client import (
    FLClientError,
    FederatedLearningClient,
    GatewayFLFleet,
)
from simulator.fl_identity import (
    GatewayIdentityRegistry,
    candidate_worker_id,
    sanitize_component,
)
from simulator.fl_storage import FLStorageComponent

WORKER_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]+$")

NODES = {
    "node1": 2010,
    "node2": 2011,
    "node3": 2012,
    "node4": 2013,
    "node5": 2014,
}


def _config() -> dict[str, Any]:
    return {
        "nodes": dict(NODES),
        "features": ["pm25", "temp", "rh"],
        "train_fraction": 0.8,
        "val_fraction_of_train": 0.1,
        "scaler": {
            "feature_min": [0.0, -10.0, 0.0],
            "feature_max": [500.0, 40.0, 100.0],
            "pm25_clip": 500.0,
        },
        "federated": {
            "training_nodes": ["node1", "node2", "node3", "node4"],
            "inference_only_nodes": ["node5"],
        },
    }


def _raw(rows_per_year: int = 60) -> pd.DataFrame:
    frames = []
    for year in (2010, 2011, 2012, 2013, 2014):
        timestamps = pd.date_range(
            f"{year}-01-01", periods=rows_per_year, freq="h"
        )
        values = np.arange(rows_per_year, dtype=float) + (year - 2010) * 1000.0
        frames.append(
            pd.DataFrame(
                {
                    "year": year,
                    "timestamp": timestamps,
                    "pm2.5": values % 300.0,
                    "temp": 10.0,
                    "rh": 50.0,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------- identities
def test_worker_ids_are_valid_deterministic_and_distinct() -> None:
    first = candidate_worker_id("gateway-01")
    assert first == candidate_worker_id("gateway-01")
    assert WORKER_TOKEN.match(first)
    assert first.startswith("gw-")
    assert candidate_worker_id("gateway-01") != candidate_worker_id("gateway-02")
    # Hostile characters are sanitised rather than leaking into topics.
    hostile = candidate_worker_id("gateway /with +bad#chars")
    assert WORKER_TOKEN.match(hostile)
    assert sanitize_component("  Gateway 01  ") == "gateway-01"


def test_identity_registry_is_idempotent_and_collision_safe() -> None:
    registry = GatewayIdentityRegistry()
    first = registry.assign("gateway-01")
    assert registry.assign("gateway-01") == first
    second = registry.assign("gateway-02")
    assert first.worker_id != second.worker_id
    assert registry.worker_for("gateway-01") == first.worker_id
    assert registry.gateway_for_worker(second.worker_id) == "gateway-02"


# --------------------------------------------------------------- partitions
def test_gateway_allocations_cover_every_shard_exactly_once() -> None:
    raw = _raw()
    config = _config()
    years = training_years(config)
    shard_count = max(3, len(years))
    allocations = gateway_shard_allocations(config, raw, gateway_count=3)

    assert len(allocations) == 3
    flattened = list(itertools.chain.from_iterable(allocations))
    assert len(flattened) == shard_count
    assert {item.shard_index for item in flattened} == set(range(shard_count))
    # Every gateway owns at least one shard and no shard is duplicated.
    assert all(bucket for bucket in allocations)
    # Allocation is deterministic, not thread/time dependent.
    assert gateway_shard_allocations(config, raw, gateway_count=3) == allocations


def test_gateway_partitions_have_disjoint_real_windows() -> None:
    raw = _raw()
    config = _config()
    partitions = [
        prepare_gateway_partition(
            raw, config, gateway_count=3, gateway_index=index, window_hours=3
        )
        for index in range(3)
    ]

    assert [item["gateway_index"] for item in partitions] == [0, 1, 2]
    assert all(item["n_samples"] > 0 for item in partitions)
    assert all(item["n_val"] > 0 for item in partitions)
    assert all(item["shard_indices"] for item in partitions)

    train_windows: list[pd.Timestamp] = []
    val_windows: list[pd.Timestamp] = []
    for item in partitions:
        prepared = item["prepared"]
        assert prepared["X_train"].shape[1] == 3
        assert np.isfinite(prepared["X_train"]).all()
        train_ts = [pd.Timestamp(value) for value in prepared["train_timestamps"]]
        val_ts = [pd.Timestamp(value) for value in prepared["val_timestamps"]]
        assert train_ts == sorted(train_ts)
        assert val_ts == sorted(val_ts)
        assert max(train_ts) < min(val_ts)
        train_windows.extend(train_ts)
        val_windows.extend(val_ts)

    assert len(set(train_windows)) == len(train_windows), "windows overlap"
    assert len(set(val_windows)) == len(val_windows), "validation windows overlap"
    assert not set(train_windows) & set(val_windows)


# ------------------------------------------------------------------- fleet
class _FakeNode:
    instances: list["_FakeNode"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._stop = kwargs["stop_event"]
        self._worker_state = "available"
        self._round_number = None
        self._dataset_label = "gateway-simulation"
        self.year = 2010
        self.years = [2010]
        # gateway_index is passed by FederatedLearningClient._build_node()
        # shard_index is also passed; use whichever is available
        shard_index = int(kwargs.get("shard_index", kwargs.get("gateway_index", 0)))
        self.n_samples = 10 * (shard_index + 1)
        self.n_val = shard_index + 1
        self.prepared = None
        self.model = None
        self._partition_info = {
            "years": [2010],
            "shard_indices": [shard_index],
            "n_samples": self.n_samples,
            "n_val": self.n_val,
            "source_rows": 20,
        }
        self.finished = threading.Event()
        _FakeNode.instances.append(self)

    def _load_training_state(self) -> None:
        return None

    def run(self) -> None:
        self._stop.wait(timeout=10)
        self.finished.set()


def test_fleet_assigns_stable_distinct_partitions(tmp_path) -> None:
    _FakeNode.instances.clear()
    fleet = GatewayFLFleet(gateway_count=3, node_factory=_FakeNode)
    storage = {
        gateway_id: FLStorageComponent(gateway_id, root=tmp_path)
        for gateway_id in ("gateway-01", "gateway-02", "gateway-03")
    }
    clients = {
        gateway_id: fleet.start(gateway_id, fl_storage=storage[gateway_id])
        for gateway_id in storage
    }
    try:
        assert [client.shard_index for client in clients.values()] == [0, 1, 2]
        assert [client.shard_count for client in clients.values()] == [3, 3, 3]
        assert len({client.worker_id for client in clients.values()}) == 3
        assert all(client.running for client in clients.values())
        # Each client built exactly one node with its own stop event.
        nodes = [
            node
            for node in _FakeNode.instances
            if node.kwargs["node_id"] in {client.worker_id for client in clients.values()}
        ]
        assert len(nodes) == 3
        assert len({id(node._stop) for node in nodes}) == 3
        assert all(node.kwargs["gateway_count"] == 3 for node in nodes)
        assert all(node.kwargs["fl_storage"] is not None for node in nodes)

        # A gateway's partition index is never reused while it is running.
        with np.testing.assert_raises(FLClientError):
            fleet.start("gateway-01")

        # Dropping and restarting one gateway keeps the survivors' indices.
        assert fleet.stop("gateway-02") is not None
        survivor_indices = {
            gateway_id: client.shard_index
            for gateway_id, client in fleet._clients.items()
        }
        assert survivor_indices == {"gateway-01": 0, "gateway-03": 2}
        restarted = fleet.start("gateway-02", fl_storage=storage["gateway-02"])
        assert restarted.shard_index == 1
        stats = fleet.stats()
        assert stats["partitions"] == {
            "gateway-01": 0,
            "gateway-02": 1,
            "gateway-03": 2,
        }
        assert len(stats["clients"]) == 3
    finally:
        assert len(fleet.stop_all()) == 3


def test_gateway_client_reports_snapshot_and_stops(tmp_path) -> None:
    client = FederatedLearningClient(
        "gateway-01",
        shard_index=0,
        shard_count=3,
        fl_storage=FLStorageComponent("gateway-01", root=tmp_path),
        node_factory=_FakeNode,
    )
    client.start()
    try:
        snapshot = client.snapshot()
        assert snapshot["gateway_id"] == "gateway-01"
        assert snapshot["worker_id"] == client.worker_id
        assert snapshot["shard_index"] == 0
        assert snapshot["shard_count"] == 3
        assert snapshot["running"] is True
        assert snapshot["state"] == "running"
        assert snapshot["n_samples"] == 10
        assert snapshot["storage"]["directory"].startswith(str(tmp_path))
    finally:
        assert client.stop()["state"] == "offline"
    assert client.running is False


# ------------------------------------------------------------- engine wiring
class _FakeFleetClient:
    def __init__(self, gateway_id: str, *, index: int, count: int, storage: Any):
        self.gateway_id = gateway_id
        self.worker_id = f"gw-{gateway_id}-0000000000"
        self.gateway_index = index
        self.gateway_count = count
        self.storage = storage
        self.running = False
        self.state = "idle"

    def start(self) -> None:
        self.running = True
        self.state = "running"

    def stop(self, timeout: float = 10.0) -> bool:
        self.running = False
        self.state = "stopped"
        return True

    def stats(self) -> dict[str, Any]:
        return {
            "gateway_id": self.gateway_id,
            "worker_id": self.worker_id,
            "shard_index": self.gateway_index,
            "shard_count": self.gateway_count,
            "state": self.state,
            "worker_state": "available" if self.running else None,
            "running": self.running,
            "current_round": None,
            "last_error": None,
            "dummy": False,
            "starts": 1,
            "year": 2010,
            "years": [2010],
            "n_samples": 10 * (self.gateway_index + 1),
            "n_val": self.gateway_index + 1,
            "partition": {
                "years": [2010],
                "shard_indices": [self.gateway_index],
                "n_samples": 10 * (self.gateway_index + 1),
                "n_val": self.gateway_index + 1,
                "source_rows": 20,
            },
            "storage": {"checkpoint_count": 0, "rounds_recorded": 0},
        }

    snapshot = stats


class _FakeFleet:
    instances: list["_FakeFleet"] = []

    def __init__(self, *, config_path: str | None = None, gateway_count: int) -> None:
        self.config_path = config_path
        self.gateway_count = gateway_count
        self._clients: dict[str, _FakeFleetClient] = {}
        _FakeFleet.instances.append(self)

    def client(self, gateway_id: str) -> _FakeFleetClient | None:
        return self._clients.get(gateway_id)

    def start(self, gateway_id: str, *, fl_storage: Any = None, **_: Any):
        index = len(self._clients)
        client = _FakeFleetClient(
            gateway_id, index=index, count=self.gateway_count, storage=fl_storage
        )
        client.start()
        self._clients[gateway_id] = client
        return client

    def stop(self, gateway_id: str, *, timeout: float = 10.0) -> bool:
        client = self._clients.get(gateway_id)
        return True if client is None else client.stop(timeout)

    def stats(self) -> dict[str, Any]:
        return {
            "gateway_count": self.gateway_count,
            "partitions": {
                gateway_id: client.gateway_index
                for gateway_id, client in self._clients.items()
            },
            "clients": {
                gateway_id: client.stats()
                for gateway_id, client in self._clients.items()
            },
        }


def test_engine_starts_one_isolated_client_per_gateway(monkeypatch, tmp_path) -> None:
    from simulator import fl_client as fl_module

    _FakeFleet.instances.clear()
    monkeypatch.setattr(fl_module, "GatewayFLFleet", _FakeFleet)
    simulator = NetworkSimulator()
    for gateway_id, gateway in simulator._gateways.items():
        gateway.fl_storage = FLStorageComponent(gateway_id, root=tmp_path)

    payload = simulator.start_fl_clients()
    try:
        assert payload["available"] is True
        assert payload["count"] == 3
        gateways = payload["gateways"]
        assert {item["gateway_id"] for item in gateways} == {
            "gateway-01",
            "gateway-02",
            "gateway-03",
        }
        assert sorted(item["gateway_index"] for item in gateways) == [0, 1, 2]
        assert all(item["running"] for item in gateways)
        assert all(item["n_samples"] > 0 for item in gateways)
        # Telemetry FL storage and client are attached but telemetry components
        # are untouched: the six stats blocks still exist.
        for gateway in simulator._gateways.values():
            assert gateway.fl_client is not None
            assert {
                "sensor_ingestion",
                "device_manager",
                "local_storage",
                "communication",
                "network_monitor",
                "forwarding",
            } <= set(gateway.get_stats())
            assert gateway.to_dict()["fl_client"] is not None

        stopped = simulator.stop_fl_clients()
        assert sorted(stopped["stopped"]) == ["gateway-01", "gateway-02", "gateway-03"]
        assert all(gateway.fl_client is None for gateway in simulator._gateways.values())
    finally:
        simulator.stop_fl_clients()


def test_gateway_stop_stops_attached_fl_client() -> None:
    simulator = NetworkSimulator()
    gateway = simulator._gateways["gateway-01"]
    fake = _FakeFleetClient("gateway-01", index=0, count=3, storage=None)
    fake.start()
    gateway.attach_fl_client(fake)
    assert gateway.to_dict()["fl_client"]["gateway_id"] == "gateway-01"
    gateway.stop()
    assert fake.running is False
    assert gateway.fl_client is None
