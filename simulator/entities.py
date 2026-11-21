"""Domain entities for the simulated network.

Only plain Python is used here.  The dashboard API, sensor generator, and
simulation engine all share these objects, so a future routing stack has one
canonical representation of a sensor, a gateway, and a reading.

Readings produced here are always labelled ``simulated``.  They are not
connected to the trained PM2.5 model or to any physical hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PM25_RANGE = (0.0, 500.0)
PM10_RANGE = (0.0, 600.0)
TEMPERATURE_RANGE = (-10.0, 60.0)
HUMIDITY_RANGE = (0.0, 100.0)
BATTERY_RANGE = (0.0, 100.0)


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with a ``Z`` suffix."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    return max(low, min(high, value))


@dataclass(frozen=True)
class Position:
    """Logical network location.

    The units are deliberately arbitrary.  The default topology uses a 0-100
    by 0-70 canvas; the frontend scales it to the available width.
    """

    x: float = 50.0
    y: float = 35.0
    location: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"x": float(self.x), "y": float(self.y), "location": self.location}


@dataclass(frozen=True)
class SensorReading:
    """One simulated air-quality sample from a sensor node."""

    timestamp: str
    pm25: float
    pm10: float
    temperature_c: float
    humidity_pct: float
    simulated: bool = True
    source: str = "simulated_sensor"

    def validate(self) -> None:
        """Raise ``ValueError`` if a value is outside its physical range."""
        checks = (
            ("pm25", self.pm25, PM25_RANGE),
            ("pm10", self.pm10, PM10_RANGE),
            ("temperature_c", self.temperature_c, TEMPERATURE_RANGE),
            ("humidity_pct", self.humidity_pct, HUMIDITY_RANGE),
        )
        for name, value, (low, high) in checks:
            if not low <= float(value) <= high:
                raise ValueError(
                    f"{name}={value!r} is outside the simulated range "
                    f"[{low}, {high}]"
                )
        if not self.timestamp:
            raise ValueError("a simulated reading needs a timestamp")

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "pm25": round(float(self.pm25), 2),
            "pm10": round(float(self.pm10), 2),
            "temperature_c": round(float(self.temperature_c), 2),
            "humidity_pct": round(float(self.humidity_pct), 2),
            "units": {"pm25": "ug/m3", "pm10": "ug/m3", "temperature": "C", "humidity": "%"},
            "simulated": bool(self.simulated),
            "source": self.source,
            "label": "SIMULATED",
        }


@dataclass
class SensorNode:
    """A simulated sensor endpoint.

    Sensor nodes are *not* federated-learning workers in this stack.  They only
    produce readings and participate in the network graph.
    """

    node_id: str
    name: str
    gateway_id: str | None = None
    position: Position = field(default_factory=Position)
    available: bool = True
    battery_level: float = 100.0
    transmission_range_m: float = 250.0
    neighbors: list[str] = field(default_factory=list)
    last_seen: str | None = None
    data_source: str = "simulated_sensor"
    latest_reading: SensorReading | None = None
    reading_count: int = 0
    node_type: str = field(default="sensor", init=False)

    def record_reading(self, reading: SensorReading) -> None:
        reading.validate()
        self.latest_reading = reading
        self.reading_count += 1
        self.last_seen = reading.timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type,
            "gateway_id": self.gateway_id,
            "position": self.position.to_dict(),
            "available": bool(self.available),
            "battery_level": round(float(self.battery_level), 2),
            "transmission_range_m": float(self.transmission_range_m),
            "neighbors": sorted(self.neighbors),
            "last_seen": self.last_seen,
            "data_source": self.data_source,
            "reading_count": self.reading_count,
            "latest_reading": (
                self.latest_reading.to_dict() if self.latest_reading else None
            ),
        }


@dataclass
class LocalStorageStatus:
    """Very small storage model for a gateway."""

    capacity_mb: float = 512.0
    used_mb: float = 0.0
    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        used_ratio = self.used_mb / self.capacity_mb if self.capacity_mb else 0.0
        return {
            "capacity_mb": float(self.capacity_mb),
            "used_mb": round(float(self.used_mb), 2),
            "used_pct": round(min(100.0, used_ratio * 100.0), 2),
            "status": self.status,
        }


@dataclass
class GatewayHealth:
    """Lightweight health information shown by the dashboard."""

    status: str = "healthy"
    cpu_load_pct: float = 12.0
    memory_used_pct: float = 24.0
    uptime_sec: float = 0.0
    error_count: int = 0
    last_heartbeat: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cpu_load_pct": round(float(self.cpu_load_pct), 2),
            "memory_used_pct": round(float(self.memory_used_pct), 2),
            "uptime_sec": round(float(self.uptime_sec), 2),
            "error_count": self.error_count,
            "last_heartbeat": self.last_heartbeat,
        }


@dataclass
class GatewayNode:
    """A simulated gateway, distinct from a sensor node."""

    gateway_id: str
    name: str
    position: Position = field(default_factory=Position)
    available: bool = True
    transmission_range_m: float = 600.0
    neighbors: list[str] = field(default_factory=list)
    connected_sensor_count: int = 0
    local_storage: LocalStorageStatus = field(default_factory=LocalStorageStatus)
    health: GatewayHealth = field(default_factory=GatewayHealth)
    last_seen: str | None = None
    node_type: str = field(default="gateway", init=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.gateway_id,
            "gateway_id": self.gateway_id,
            "name": self.name,
            "node_type": self.node_type,
            "position": self.position.to_dict(),
            "available": bool(self.available),
            "transmission_range_m": float(self.transmission_range_m),
            "neighbors": sorted(self.neighbors),
            "connected_sensor_count": self.connected_sensor_count,
            "local_storage": self.local_storage.to_dict(),
            "health": self.health.to_dict(),
            "last_seen": self.last_seen,
        }


NetworkNode = SensorNode | GatewayNode


def set_battery_level(node: SensorNode, level: float) -> None:
    """Clamp and assign a simulated battery percentage."""
    node.battery_level = _clamp(float(level), BATTERY_RANGE)


__all__ = [
    "BATTERY_RANGE",
    "HUMIDITY_RANGE",
    "PM10_RANGE",
    "PM25_RANGE",
    "TEMPERATURE_RANGE",
    "GatewayHealth",
    "GatewayNode",
    "LocalStorageStatus",
    "NetworkNode",
    "Position",
    "SensorNode",
    "SensorReading",
    "set_battery_level",
    "utc_now_iso",
]
