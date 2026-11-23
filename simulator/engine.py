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
from pathlib import Path
from typing import Any

from simulator.entities import (
    GatewayNode,
    LocalStorageStatus,
    Position,
    SensorNode,
    utc_now_iso,
)
from simulator.links import NetworkLink
from simulator.entities import SensorReading
from simulator.gateway import Gateway, create_gateway
from simulator.rpl import create_rpl_engine, RPLEngine
from simulator.sensor_data import SensorDataConfig, SensorDataGenerator
from simulator.topology_config import build_topology, default_topology_config
from simulator.trickle import TrickleTimer, create_trickle_params_for_dio

SIMULATION_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

FL_GATEWAYS_NOTE = (
    "Each gateway is an independent FL client on a disjoint partition of the "
    "historical training years. Raw rows never leave the gateway; only weights "
    "and validation scalars are uploaded. Telemetry, RPL, and Trickle are "
    "separate components and stay untouched."
)


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

        # RPL and Trickle integration
        self.rpl_engine: RPLEngine = create_rpl_engine(self.topology, self.config.seed)
        self._trickle_timers: dict[str, dict[str, TrickleTimer]] = {}  # node_id -> {dodag_id: timer}
        self._dio_params = create_trickle_params_for_dio()

        # Gateway instances
        self._gateways: dict[str, Gateway] = {}
        self._mqtt_broker_host = "localhost"
        self._mqtt_broker_port = 1883

        # Create Gateway wrapper instances for each GatewayNode in topology
        for gateway_node in self.topology.gateway_nodes():
            gateway_id = gateway_node.gateway_id
            gateway_instance = create_gateway(
                gateway_node,
                self.topology,
                self.rpl_engine,
                self._mqtt_broker_host,
                self._mqtt_broker_port,
            )
            gateway_instance.initialize_dodag()
            self._gateways[gateway_id] = gateway_instance
            self._init_trickle_for_node(gateway_id, gateway_instance.dodag_id)

        # Dedicated federated-learning clients, one per gateway (Stack 3).
        # They are intentionally independent of the telemetry components and
        # are only created when explicitly enabled.  The fleet owns the
        # deterministic gateway -> partition mapping, so dropping and restarting
        # one gateway never renumbers the others.
        self._fl_fleet: Any = None

        self._ensure_generators()
        self._initialize_rpl()

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
        self.stop_fl_clients()
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
    def _forward_sensor_readings(self, now: float) -> None:
        """Forward sensor readings to gateways via RPL upward routes."""
        import time
        for gateway in self._gateways.values():
            if not gateway.gateway_node.available:
                continue

            sensors = gateway.device_manager.list_sensors(active_only=True)

            for sensor_reg in sensors:
                sensor_id = sensor_reg.node_id
                sensor = self.topology.get_sensor(sensor_id)

                if not sensor.available or not sensor.latest_reading:
                    continue

                # Forward reading to gateway via RPL upward route
                reading = sensor.latest_reading
                route = gateway.forwarding.get_upward_route(sensor_id)

                if route and len(route) >= 2 and route[-1] == gateway.gateway_id:
                    # Route exists - deliver to gateway
                    gateway.receive_sensor_telemetry(sensor_id, reading, route)

                    # Mark as forwarded in local storage
                    gateway.local_storage.mark_forwarded(sensor_id, time.time())

    def _process_gateway_outbound(self, now: float) -> None:
        """Process gateway outbound telemetry (MQTT publishing) and health checks."""
        for gateway in self._gateways.values():
            if not gateway.gateway_node.available:
                continue

            # Process pending telemetry for MQTT publishing
            gateway.process_outbound_telemetry()

            # Check network health and trigger repairs
            gateway.check_network_health(now)

            # Publish status and health periodically
            if self._tick_count % 6 == 0:  # Every ~30 seconds (6 * 5s)
                gateway.publish_status()
                gateway.publish_health()

    def advance(self, seconds: float | None = None) -> dict[str, Any]:
        """Advance simulated time, generate due readings, update availability, forward packets."""
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

            # RPL/Trickle processing
            now = self._tick_count * self.config.interval_seconds
            self._process_trickle_timers(now)
            self._update_rpl_state(now)

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

            # Forward sensor readings to gateways via RPL routes
            self._forward_sensor_readings(now)

            # Process gateway outbound (MQTT, health checks)
            self._process_gateway_outbound(now)

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

            # Create Gateway instance with all six components
            gateway_instance = create_gateway(
                gateway,
                self.topology,
                self.rpl_engine,
                self._mqtt_broker_host,
                self._mqtt_broker_port,
            )
            self._gateways[assigned_id] = gateway_instance

            # Initialize DODAG for this gateway
            gateway_instance.initialize_dodag()
            self._init_trickle_for_node(assigned_id, gateway_instance.dodag_id)

            return gateway_instance.to_dict()

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

            # Remove gateway instance if it was a gateway
            if node_id in self._gateways:
                gateway = self._gateways.pop(node_id)
                gateway.detach_fl_client()
                if self._fl_fleet is not None:
                    self._fl_fleet.stop(node_id)
                gateway.stop()

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
                "fl_clients": self.fl_clients_payload(),
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

    # ------------------------------------------------- federated-learning clients
    def start_fl_clients(
        self,
        *,
        config_path: str | Path | None = None,
        window_hours: int | None = None,
        host: str | None = None,
        port: int | None = None,
        seed: int | None = None,
        gateway_ids: list[str] | None = None,
        gateway_count: int | None = None,
    ) -> dict[str, Any]:
        """Start one dedicated FL client per (available) gateway.

        A gateway's partition is a deterministic function of the sorted gateway
        list, not of the order clients were started.  Stopping one gateway
        therefore never renumbers the survivors: restarting it gives back the
        same partition.  Each client wraps the existing ``FederatedNode`` on the
        gateway's own MQTT connection; telemetry components are untouched.
        """
        from simulator.fl_client import GatewayFLFleet

        with self._lock:
            available = {
                gateway_id: gateway
                for gateway_id, gateway in self._gateways.items()
                if gateway.gateway_node.available
            }
            if gateway_ids is not None:
                missing = [gid for gid in gateway_ids if gid not in available]
                if missing:
                    raise ValueError(
                        "no available gateway(s): " + ", ".join(sorted(missing))
                    )
                order = list(dict.fromkeys(gateway_ids))
            else:
                order = sorted(available)
            if not order:
                raise ValueError("the topology has no available gateways")
            count = int(gateway_count or len(available))
            if count < len(available):
                raise ValueError(
                    f"gateway_count={count} is smaller than the "
                    f"{len(available)} available gateways"
                )
            fleet = self._fl_fleet
            if fleet is None or fleet.gateway_count != count:
                if fleet is not None and any(
                    client.running for client in fleet._clients.values()
                ):
                    raise ValueError(
                        "stop the running FL clients before changing gateway_count"
                    )
                fleet = GatewayFLFleet(
                    config_path=str(config_path) if config_path else None,
                    gateway_count=count,
                )
                self._fl_fleet = fleet

        for gateway_id in order:
            existing = fleet.client(gateway_id)
            if existing is not None and existing.running:
                available[gateway_id].attach_fl_client(existing)
                continue
            if existing is not None:
                existing.stop()
            client = fleet.start(
                gateway_id,
                fl_storage=available[gateway_id].fl_storage,
                window_hours=window_hours,
                host=host,
                port=port,
                seed=seed,
            )
            available[gateway_id].attach_fl_client(client)
        return self.fl_clients_payload()

    def stop_fl_clients(
        self, gateway_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Stop gateway FL clients (all when ``gateway_ids`` is omitted).

        Stopping is an intentional dropout: the gateway's worker state goes
        offline and the coordinator's partial-participation rules take over.
        The fleet keeps the gateway's partition index for a later restart.
        """
        with self._lock:
            fleet = self._fl_fleet
            if fleet is None:
                return {"ok": True, "stopped": [], **self.fl_clients_payload()}
            selected = (
                list(gateway_ids)
                if gateway_ids is not None
                else sorted(fleet._clients)
            )
            gateways = dict(self._gateways)
        stopped: list[str] = []
        for gateway_id in selected:
            if gateway_id not in fleet._clients:
                continue
            gateway = gateways.get(gateway_id)
            if gateway is not None:
                gateway.detach_fl_client()
            try:
                fleet.stop(gateway_id)
            finally:
                stopped.append(gateway_id)
        return {"ok": True, "stopped": stopped, **self.fl_clients_payload()}

    def fl_clients_payload(self) -> dict[str, Any]:
        """Read-only dashboard view of every gateway FL client."""
        with self._lock:
            fleet = self._fl_fleet
        if fleet is None:
            return {
                "available": False,
                "count": 0,
                "gateways": [],
                "note": FL_GATEWAYS_NOTE,
            }
        stats = fleet.stats()
        gateways: list[dict[str, Any]] = []
        for gateway_id, client_stats in sorted(stats["clients"].items()):
            partition = client_stats.get("partition") or {}
            years = [int(year) for year in partition.get("years") or []]
            gateways.append(
                {
                    **client_stats,
                    "gateway_id": gateway_id,
                    "worker_id": client_stats.get("worker_id"),
                    "gateway_index": client_stats.get("shard_index"),
                    "gateway_count": client_stats.get("shard_count"),
                    "years": years,
                    "year": years[0] if years else client_stats.get("year"),
                    "shard_indices": partition.get("shard_indices") or [],
                    "n_samples": int(
                        client_stats.get("n_samples")
                        or partition.get("n_samples")
                        or 0
                    ),
                    "n_val": int(
                        client_stats.get("n_val") or partition.get("n_val") or 0
                    ),
                    "source_rows": partition.get("source_rows"),
                    "current_round": client_stats.get("current_round"),
                    "state": client_stats.get("state"),
                    "worker_state": client_stats.get("worker_state"),
                }
            )
        return {
            "available": bool(gateways),
            "count": len(gateways),
            "gateway_count": stats.get("gateway_count"),
            "partitions": stats.get("partitions", {}),
            "gateways": gateways,
            "note": FL_GATEWAYS_NOTE,
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

    def _initialize_rpl(self) -> None:
        """Initialize RPL DODAGs for each gateway and start Trickle timers."""
        with self._lock:
            # Initialize DODAG for each gateway
            for gateway in self.topology.gateway_nodes():
                self.rpl_engine.initialize_dodag(gateway.gateway_id)
                self._init_trickle_for_node(gateway.gateway_id, gateway.gateway_id)

            # Initialize Trickle for sensors (they'll join via DIS/DIO)
            for sensor in self.topology.sensor_nodes():
                self._init_trickle_for_node(sensor.node_id, sensor.node_id)

    def _init_trickle_for_node(self, node_id: str, dodag_id: str) -> None:
        """Initialize Trickle timer for a node/DODAG pair."""
        if node_id not in self._trickle_timers:
            self._trickle_timers[node_id] = {}
        timer = TrickleTimer(self._dio_params)
        timer.initialize(0.0, self._dio_params)
        self._trickle_timers[node_id][dodag_id] = timer

    def _process_trickle_timers(self, now: float) -> dict[str, list]:
        """Process all Trickle timers, return messages to send."""
        messages = {"dio": [], "dis": [], "dao": []}

        with self._lock:
            for node_id, dodag_timers in self._trickle_timers.items():
                for dodag_id, timer in dodag_timers.items():
                    should_tx, interval_expired = timer.step(now)

                    if should_tx:
                        # Determine message type based on node state
                        node_state = self.rpl_engine.nodes_state.get(node_id)
                        if node_state and node_state.is_root:
                            # Root sends DIO
                            dodag_config = self.rpl_engine.dodag_configs.get(dodag_id)
                            if dodag_config and node_state.rank:
                                dio = dodag_config  # This needs proper DIO creation
                                messages["dio"].append({
                                    "source": node_id,
                                    "dodag_id": dodag_id,
                                    "type": "dio",
                                })
                        elif node_state and node_state.joined_dodag:
                            # Joined node sends DIO
                            messages["dio"].append({
                                "source": node_id,
                                "dodag_id": dodag_id,
                                "type": "dio",
                            })
                        elif node_state and not node_state.joined_dodag:
                            # Not joined - send DIS
                            messages["dis"].append({
                                "source": node_id,
                                "dodag_id": dodag_id,
                                "type": "dis",
                            })

                        timer.on_tx(now)

                    if interval_expired:
                        # Interval doubled, continue
                        pass

        return messages

    def _update_rpl_state(self, now: float) -> None:
        """Update RPL ranks and routing for all nodes."""
        with self._lock:
            # Process all DODAGs
            for dodag_id in self.rpl_engine.dodag_configs:
                # Update ranks for all nodes in this DODAG
                for node_id in self.rpl_engine.nodes_state:
                    state = self.rpl_engine.nodes_state[node_id]
                    if state.dodag_id == dodag_id or (state.is_root and state.dodag_id == dodag_id):
                        self.rpl_engine.update_node_rank(node_id, dodag_id, now)

                # Update routing tables via DAO propagation (simplified)
                # In a full implementation, DAOs would be sent up the tree
                # For now, compute routes on demand

    def _next_id(self, prefix: str) -> str:
        highest = 0
        for node_id in (*self.topology.nodes, *self.topology.links):
            stem, _, suffix = str(node_id).rpartition("-")
            if stem == prefix and suffix.isdigit():
                highest = max(highest, int(suffix))
        return f"{prefix}-{highest + 1:02d}"

    # ---------------------------- RPL/Trickle API methods
    def get_rpl_state(self, node_id: str) -> dict[str, Any]:
        """Get complete RPL state for a node."""
        with self._lock:
            return self.rpl_engine.get_node_rpl_state(node_id)

    def get_dodag_summary(self, dodag_id: str) -> dict[str, Any]:
        """Get DODAG summary."""
        with self._lock:
            return self.rpl_engine.get_dodag_summary(dodag_id)

    def get_all_rpl_state(self) -> dict[str, Any]:
        """Get RPL state for all nodes."""
        with self._lock:
            return {
                "nodes": {
                    node_id: self.rpl_engine.get_node_rpl_state(node_id)
                    for node_id in self.rpl_engine.nodes_state
                },
                "dodags": {
                    dodag_id: self.rpl_engine.get_dodag_summary(dodag_id)
                    for dodag_id in self.rpl_engine.dodag_configs
                },
            }

    def get_trickle_state(self, node_id: str, dodag_id: str) -> dict[str, Any] | None:
        """Get Trickle timer state for a node/DODAG."""
        with self._lock:
            timers = self._trickle_timers.get(node_id, {})
            timer = timers.get(dodag_id)
            if timer:
                now = self._tick_count * self.config.interval_seconds
                return timer.get_state(now)
            return None

    def get_all_trickle_state(self) -> dict[str, Any]:
        """Get Trickle state for all nodes."""
        with self._lock:
            now = self._tick_count * self.config.interval_seconds
            result = {}
            for node_id, dodag_timers in self._trickle_timers.items():
                result[node_id] = {}
                for dodag_id, timer in dodag_timers.items():
                    result[node_id][dodag_id] = timer.get_state(now)
            return result


__all__ = ["SIMULATION_EPOCH", "NetworkSimulator", "SimulationConfig"]
