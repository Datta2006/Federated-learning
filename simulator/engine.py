"""Simulation engine that owns the current network state.

The engine is transport-agnostic and has no frontend or MQTT imports.  The
dashboard API is a thin adapter around this class, so the same engine can later
drive RPL timers, link-failure experiments, or an MQTT gateway bridge.
"""

from __future__ import annotations

import copy
import random
import threading
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from simulator.entities import (
    GatewayNode,
    LocalStorageStatus,
    Position,
    SensorNode,
    utc_now_iso,
)
from simulator.links import NetworkLink
from simulator.sensor_data import SensorDataConfig, SensorDataGenerator
from simulator.topology_config import build_topology, default_topology_config

SIMULATION_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _iso(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True)
class SimulationConfig:
    """Runtime settings for the simulation loop."""

    interval_seconds: float = 5.0
    seed: int = 42
    history_limit: int = 240
    auto_generate_readings: bool = True
    battery_drain_pct_per_hour: float = 0.4
    node_failure_probability: float = 0.0
    link_failure_probability: float = 0.0

    def __post_init__(self) -> None:
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if self.history_limit < 1:
            raise ValueError("history_limit must be at least 1")
        if self.battery_drain_pct_per_hour < 0:
            raise ValueError("battery_drain_pct_per_hour must not be negative")
        for name in ("node_failure_probability", "link_failure_probability"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SimulationConfig:
        values = dict(raw or {})
        return cls(
            interval_seconds=float(values.get("interval_seconds", 5.0)),
            seed=int(values.get("seed", 42)),
            history_limit=int(values.get("history_limit", 240)),
            auto_generate_readings=bool(
                values.get("auto_generate_readings", True)
            ),
            battery_drain_pct_per_hour=float(
                values.get("battery_drain_pct_per_hour", 0.4)
            ),
            node_failure_probability=float(
                values.get("node_failure_probability", 0.0)
            ),
            link_failure_probability=float(
                values.get("link_failure_probability", 0.0)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_seconds": self.interval_seconds,
            "seed": self.seed,
            "history_limit": self.history_limit,
            "auto_generate_readings": self.auto_generate_readings,
            "battery_drain_pct_per_hour": self.battery_drain_pct_per_hour,
            "node_failure_probability": self.node_failure_probability,
            "link_failure_probability": self.link_failure_probability,
        }


class NetworkSimulator:
    """Thread-safe owner of the simulated network topology and clock."""

    def __init__(
        self,
        topology_config: dict[str, Any] | None = None,
        config: SimulationConfig | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._topology_config = copy.deepcopy(
            topology_config or default_topology_config()
        )
        self.config = config or SimulationConfig.from_dict(
            self._topology_config.get("simulation", {})
        )
        raw_sensor = self._topology_config.get("sensor_data") or {}
        self.sensor_config = SensorDataConfig(
            **{
                key: float(value)
                for key, value in raw_sensor.items()
                if key
                in {
                    "pm25_volatility",
                    "pm10_volatility",
                    "temperature_volatility",
                    "humidity_volatility",
                    "mean_reversion",
                }
            }
        )
        self.topology = build_topology(self._topology_config)
        self._generators: dict[str, SensorDataGenerator] = {}
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.config.history_limit)
        )
        self._running = False
        self._simulated_time = SIMULATION_EPOCH
        self._seconds_since_reading = 0.0
        self._tick_count = 0
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._rng = random.Random(self.config.seed)
        self._reading_total = 0
        self._ensure_generators()

    # ------------------------------------------------------------ lifecycle
    def start(self) -> dict[str, Any]:
        with self._lock:
            if not self._running:
                self._running = True
                self._started_at = utc_now_iso()
                self._stopped_at = None
                self._refresh_availability_timestamps()
                if self.config.auto_generate_readings:
                    self._emit_readings()
            return self.status_payload()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._running = False
            self._stopped_at = utc_now_iso()
            return self.status_payload()

    def reset(self) -> dict[str, Any]:
        """Return to the original configured topology and clock."""
        with self._lock:
            self._running = False
            self.topology = build_topology(self._topology_config)
            self._generators = {}
            self._history = defaultdict(lambda: deque(maxlen=self.config.history_limit))
            self._simulated_time = SIMULATION_EPOCH
            self._seconds_since_reading = 0.0
            self._tick_count = 0
            self._started_at = None
            self._stopped_at = utc_now_iso()
            self._rng = random.Random(self.config.seed)
            self._reading_total = 0
            self._ensure_generators()
            return self.status_payload()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    # --------------------------------------------------------------- clock
    def advance(self, seconds: float | None = None) -> dict[str, Any]:
        """Advance simulated time, generate due readings, update availability."""
        with self._lock:
            step = self.config.interval_seconds if seconds is None else float(seconds)
            if step < 0:
                raise ValueError("simulation time cannot move backwards")
            if step == 0:
                return self.status_payload()

            self._simulated_time += timedelta(seconds=step)
            self._tick_count += 1
            self._drain_batteries(step)
            self._refresh_health(step)
            self._refresh_availability_timestamps()

            if self.config.auto_generate_readings:
                self._seconds_since_reading += step
                due = int(self._seconds_since_reading // self.config.interval_seconds)
                if due > 0:
                    remainder = self._seconds_since_reading % (
                        self.config.interval_seconds
                    )
                    newest_due = self._simulated_time - timedelta(seconds=remainder)
                    # Emit at interval boundaries, oldest first.
                    for index in range(due):
                        timestamp = newest_due - timedelta(
                            seconds=self.config.interval_seconds * (due - 1 - index)
                        )
                        self._emit_readings(timestamp)
                    self._seconds_since_reading = remainder
            self._maybe_apply_failures()
            return self.status_payload()

    def advance_if_running(self, seconds: float) -> dict[str, Any] | None:
        with self._lock:
            if not self._running:
                return None
            return self.advance(seconds)

    # --------------------------------------------------------------- nodes
    def create_gateway_node(
        self,
        *,
        gateway_id: str | None = None,
        name: str | None = None,
        position: Position | None = None,
        available: bool = True,
        transmission_range_m: float = 600.0,
        storage_capacity_mb: float = 512.0,
        storage_used_mb: float = 0.0,
    ) -> dict[str, Any]:
        with self._lock:
            assigned_id = gateway_id or self._next_id("gateway")
            gateway = GatewayNode(
                gateway_id=assigned_id,
                name=name or f"Gateway {assigned_id}",
                position=position or Position(),
                available=available,
                transmission_range_m=float(transmission_range_m),
                local_storage=LocalStorageStatus(
                    capacity_mb=float(storage_capacity_mb),
                    used_mb=float(storage_used_mb),
                ),
            )
            self.topology.add_gateway_node(gateway)
            return gateway.to_dict()

    def create_sensor_node(
        self,
        *,
        node_id: str | None = None,
        name: str | None = None,
        gateway_id: str | None = None,
        position: Position | None = None,
        available: bool = True,
        battery_level: float = 100.0,
        transmission_range_m: float = 250.0,
        data_source: str = "simulated_sensor",
    ) -> dict[str, Any]:
        with self._lock:
            assigned_id = node_id or self._next_id("sensor")
            sensor = SensorNode(
                node_id=assigned_id,
                name=name or f"Sensor {assigned_id}",
                gateway_id=gateway_id,
                position=position or Position(),
                available=available,
                battery_level=float(battery_level),
                transmission_range_m=float(transmission_range_m),
                data_source=data_source,
            )
            self.topology.add_sensor_node(sensor)
            self._generators.pop(assigned_id, None)
            if self._running and sensor.available and self.config.auto_generate_readings:
                self._emit_reading(sensor, self._simulated_time)
            return sensor.to_dict()

    def remove_node(self, node_id: str) -> dict[str, Any]:
        with self._lock:
            node = self.topology.remove_node(node_id)
            self._generators.pop(node_id, None)
            self._history.pop(node_id, None)
            return node.to_dict()

    def set_node_availability(
        self, node_id: str, available: bool
    ) -> dict[str, Any]:
        with self._lock:
            node = self.topology.get_node(node_id)
            node.available = bool(available)
            if node.available:
                node.last_seen = _iso(self._simulated_time)
            if isinstance(node, GatewayNode):
                node.health.status = "healthy" if node.available else "offline"
            return node.to_dict()

    def assign_gateway(
        self, sensor_id: str, gateway_id: str | None
    ) -> dict[str, Any]:
        with self._lock:
            sensor = self.topology.assign_sensor(sensor_id, gateway_id)
            return sensor.to_dict()

    # --------------------------------------------------------------- links
    def create_link(
        self,
        *,
        source: str,
        destination: str,
        link_id: str | None = None,
        quality: float = 1.0,
        etx: float = 1.0,
        latency_ms: float = 10.0,
        packet_loss: float = 0.0,
        available: bool = True,
        bandwidth_kbps: float = 250.0,
        bidirectional: bool = True,
    ) -> dict[str, Any]:
        with self._lock:
            self.topology.get_node(source)
            self.topology.get_node(destination)
            assigned_id = link_id or self._next_id("link")
            link = NetworkLink(
                link_id=assigned_id,
                source=source,
                destination=destination,
                quality=float(quality),
                etx=float(etx),
                latency_ms=float(latency_ms),
                packet_loss=float(packet_loss),
                available=available,
                bandwidth_kbps=float(bandwidth_kbps),
                bidirectional=bool(bidirectional),
            )
            self.topology.add_link(link)
            return link.to_dict()

    def remove_link(self, link_id: str) -> dict[str, Any]:
        with self._lock:
            return self.topology.remove_link(link_id).to_dict()

    def set_link_availability(
        self, link_id: str, available: bool
    ) -> dict[str, Any]:
        with self._lock:
            link = self.topology.get_link(link_id)
            link.available = bool(available)
            link.last_updated = utc_now_iso()
            return link.to_dict()

    # ------------------------------------------------------------ inspection
    def topology_payload(self) -> dict[str, Any]:
        with self._lock:
            return self.topology.snapshot()

    def nodes_payload(self) -> list[dict[str, Any]]:
        with self._lock:
            return [node.to_dict() for node in self.topology.nodes.values()]

    def gateways_payload(self) -> list[dict[str, Any]]:
        with self._lock:
            return [node.to_dict() for node in self.topology.gateway_nodes()]

    def sensors_payload(self) -> list[dict[str, Any]]:
        with self._lock:
            return [node.to_dict() for node in self.topology.sensor_nodes()]

    def links_payload(self) -> list[dict[str, Any]]:
        with self._lock:
            return [link.to_dict() for link in self.topology.links.values()]

    def readings_payload(
        self, node_id: str, limit: int = 50
    ) -> dict[str, Any]:
        with self._lock:
            sensor = self.topology.get_sensor(node_id)
            rows = list(self._history.get(node_id, ()))[-max(1, limit) :]
            return {
                "node_id": node_id,
                "simulated": True,
                "latest": (
                    sensor.latest_reading.to_dict()
                    if sensor.latest_reading
                    else None
                ),
                "readings": rows,
                "count": len(rows),
            }

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            sensor_nodes = list(self.topology.sensor_nodes())
            gateway_nodes = list(self.topology.gateway_nodes())
            return {
                "running": self._running,
                "state": "running" if self._running else "stopped",
                "simulated_time": _iso(self._simulated_time),
                "simulation_epoch": _iso(SIMULATION_EPOCH),
                "tick_count": self._tick_count,
                "reading_total": self._reading_total,
                "seconds_since_last_tick": 0.0,
                "started_at": self._started_at,
                "stopped_at": self._stopped_at,
                "topology_name": self.topology.name,
                "config": self.config.to_dict(),
                "counts": {
                    "nodes": len(self.topology.nodes),
                    "sensors": len(sensor_nodes),
                    "gateways": len(gateway_nodes),
                    "links": len(self.topology.links),
                    "online_sensors": sum(
                        1 for node in sensor_nodes if node.available
                    ),
                    "online_gateways": sum(
                        1 for node in gateway_nodes if node.available
                    ),
                    "available_links": sum(
                        1 for link in self.topology.links.values() if link.available
                    ),
                    "readings": self._reading_total,
                },
                "note": (
                    "Simulated network only. Readings are synthetic and are not "
                    "connected to the trained PM2.5 model or physical hardware."
                ),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "simulation": self.status_payload(),
                "topology": self.topology_payload(),
            }

    def configuration_payload(self) -> dict[str, Any]:
        with self._lock:
            return {
                "simulation": self.config.to_dict(),
                "sensor_data": self.sensor_config.to_dict(),
                "topology": {
                    "name": self.topology.name,
                    "description": self.topology.description,
                    "gateway_count": len(list(self.topology.gateway_nodes())),
                    "sensor_count": len(list(self.topology.sensor_nodes())),
                    "link_count": len(self.topology.links),
                },
                "ranges": {
                    "pm25": [0, 500],
                    "pm10": [0, 600],
                    "temperature_c": [-10, 60],
                    "humidity_pct": [0, 100],
                    "units": {"pm25": "ug/m3", "pm10": "ug/m3"},
                },
                "note": (
                    "Readings are generated by a seeded smooth random walk and "
                    "are explicitly marked simulated."
                ),
            }

    # -------------------------------------------------------------- internal
    def _ensure_generators(self) -> None:
        for sensor in self.topology.sensor_nodes():
            self._generator(sensor.node_id)

    def _generator(self, node_id: str) -> SensorDataGenerator:
        generator = self._generators.get(node_id)
        if generator is None:
            generator = SensorDataGenerator(
                node_id,
                seed=self.config.seed,
                config=self.sensor_config,
            )
            self._generators[node_id] = generator
        return generator

    def _emit_readings(self, at: datetime | None = None) -> None:
        timestamp = _iso(at or self._simulated_time)
        for sensor in self.topology.sensor_nodes():
            if sensor.available:
                self._emit_reading(sensor, at, timestamp=timestamp)

    def _emit_reading(
        self,
        sensor: SensorNode,
        at: datetime | None = None,
        *,
        timestamp: str | None = None,
    ) -> None:
        stamp = timestamp or _iso(at or self._simulated_time)
        reading = self._generator(sensor.node_id).generate(stamp)
        sensor.record_reading(reading)
        self._history[sensor.node_id].append(reading.to_dict())
        self._reading_total += 1

    def _refresh_availability_timestamps(self) -> None:
        stamp = _iso(self._simulated_time)
        for node in self.topology.nodes.values():
            if node.available:
                node.last_seen = stamp

    def _refresh_health(self, step: float) -> None:
        for gateway in self.topology.gateway_nodes():
            if not gateway.available:
                gateway.health.status = "offline"
                continue
            gateway.health.status = "healthy"
            gateway.health.uptime_sec += step
            gateway.health.last_heartbeat = _iso(self._simulated_time)
            gateway.health.cpu_load_pct = max(
                1.0,
                min(
                    95.0,
                    gateway.health.cpu_load_pct
                    + self._rng.uniform(-0.5, 0.5),
                ),
            )
            ratio = (
                gateway.local_storage.used_mb
                / gateway.local_storage.capacity_mb
                if gateway.local_storage.capacity_mb
                else 0.0
            )
            gateway.local_storage.status = (
                "full" if ratio >= 0.95 else "warning" if ratio >= 0.8 else "ok"
            )

    def _drain_batteries(self, step: float) -> None:
        if self.config.battery_drain_pct_per_hour <= 0:
            return
        drop = self.config.battery_drain_pct_per_hour * (step / 3600.0)
        for sensor in self.topology.sensor_nodes():
            if not sensor.available:
                continue
            sensor.battery_level = max(0.0, sensor.battery_level - drop)
            if sensor.battery_level <= 0.0:
                sensor.available = False

    def _maybe_apply_failures(self) -> None:
        if self.config.node_failure_probability > 0:
            for sensor in self.topology.sensor_nodes():
                if self._rng.random() < self.config.node_failure_probability:
                    sensor.available = not sensor.available
        if self.config.link_failure_probability > 0:
            for link in self.topology.links.values():
                if self._rng.random() < self.config.link_failure_probability:
                    link.available = not link.available
                    link.last_updated = utc_now_iso()

    def _next_id(self, prefix: str) -> str:
        highest = 0
        for node_id in (*self.topology.nodes, *self.topology.links):
            stem, _, suffix = str(node_id).rpartition("-")
            if stem == prefix and suffix.isdigit():
                highest = max(highest, int(suffix))
        return f"{prefix}-{highest + 1:02d}"


__all__ = ["SIMULATION_EPOCH", "NetworkSimulator", "SimulationConfig"]
