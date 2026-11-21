"""Configurable default topology and configuration loading.

The default network has three gateways, twelve sensors, multi-hop paths, and
alternative paths from sensors to their gateways.  It is data, not hard-coded
engine behaviour: replace the JSON structure to test another layout.

The frontend uses the logical positions only for drawing.  Links represent
simulated adjacency, not discovered RPL routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from simulator.entities import GatewayNode, LocalStorageStatus, Position, SensorNode
from simulator.links import NetworkLink
from simulator.topology import NetworkTopology


def default_topology_config() -> dict[str, Any]:
    """Return the built-in three-gateway / twelve-sensor layout."""
    return {
        "schema_version": 1,
        "name": "AirFed default field network",
        "description": (
            "Three gateways with twelve sensors. Some sensors have both a "
            "direct and a multi-hop path to their assigned gateway."
        ),
        "simulation": {
            "interval_seconds": 5.0,
            "seed": 42,
            "history_limit": 240,
            "auto_generate_readings": True,
            "battery_drain_pct_per_hour": 0.4,
            "node_failure_probability": 0.0,
            "link_failure_probability": 0.0,
        },
        "gateways": [
            _gateway("gateway-alpha", "Gateway Alpha", 18, 10, location="north-west"),
            _gateway("gateway-beta", "Gateway Beta", 50, 8, location="north"),
            _gateway("gateway-gamma", "Gateway Gamma", 82, 11, location="north-east"),
        ],
        "sensors": [
            _sensor("sensor-01", "Alpha Sensor 01", "gateway-alpha", 7, 30, 96),
            _sensor("sensor-02", "Alpha Sensor 02", "gateway-alpha", 20, 34, 88),
            _sensor("sensor-03", "Alpha Sensor 03", "gateway-alpha", 9, 50, 79),
            _sensor("sensor-04", "Alpha Sensor 04", "gateway-alpha", 30, 55, 73),
            _sensor("sensor-05", "Beta Sensor 05", "gateway-beta", 40, 28, 94),
            _sensor("sensor-06", "Beta Sensor 06", "gateway-beta", 58, 32, 86),
            _sensor("sensor-07", "Beta Sensor 07", "gateway-beta", 44, 48, 81),
            _sensor("sensor-08", "Beta Sensor 08", "gateway-beta", 62, 52, 76),
            _sensor("sensor-09", "Gamma Sensor 09", "gateway-gamma", 70, 30, 91),
            _sensor("sensor-10", "Gamma Sensor 10", "gateway-gamma", 88, 34, 84),
            _sensor("sensor-11", "Gamma Sensor 11", "gateway-gamma", 73, 52, 77),
            _sensor("sensor-12", "Gamma Sensor 12", "gateway-gamma", 91, 56, 69),
        ],
        "links": [
            # Gateway alpha cluster: sensor-04 has a direct backup plus a
            # multi-hop path through sensor-03 / sensor-01.
            _link("alpha-s01", "gateway-alpha", "sensor-01", 0.94, 1.08, 8, 0.005, 250),
            _link("alpha-s02", "gateway-alpha", "sensor-02", 0.87, 1.28, 11, 0.012, 250),
            _link("alpha-s03", "gateway-alpha", "sensor-03", 0.80, 1.48, 14, 0.02, 250),
            _link("alpha-s04-backup", "gateway-alpha", "sensor-04", 0.54, 3.20, 31, 0.11, 125),
            _link("alpha-s01-s02", "sensor-01", "sensor-02", 0.96, 1.02, 5, 0.002, 250),
            _link("alpha-s02-s03", "sensor-02", "sensor-03", 0.91, 1.12, 7, 0.006, 250),
            _link("alpha-s03-s04", "sensor-03", "sensor-04", 0.93, 1.06, 6, 0.004, 250),
            # Gateway beta cluster: sensor-08 has a backup direct link and a
            # longer path through sensor-07 and sensor-06.
            _link("beta-s05", "gateway-beta", "sensor-05", 0.92, 1.10, 9, 0.007, 250),
            _link("beta-s06", "gateway-beta", "sensor-06", 0.85, 1.33, 13, 0.018, 250),
            _link("beta-s07", "gateway-beta", "sensor-07", 0.73, 1.72, 19, 0.04, 250),
            _link("beta-s08-backup", "gateway-beta", "sensor-08", 0.49, 3.60, 36, 0.14, 125),
            _link("beta-s05-s06", "sensor-05", "sensor-06", 0.95, 1.04, 5, 0.003, 250),
            _link("beta-s06-s07", "sensor-06", "sensor-07", 0.90, 1.16, 8, 0.008, 250),
            _link("beta-s07-s08", "sensor-07", "sensor-08", 0.88, 1.22, 9, 0.01, 250),
            # Gateway gamma cluster.
            _link("gamma-s09", "gateway-gamma", "sensor-09", 0.93, 1.07, 8, 0.005, 250),
            _link("gamma-s10", "gateway-gamma", "sensor-10", 0.82, 1.44, 15, 0.025, 250),
            _link("gamma-s11", "gateway-gamma", "sensor-11", 0.70, 1.82, 21, 0.045, 250),
            _link("gamma-s12", "gateway-gamma", "sensor-12", 0.58, 2.70, 28, 0.09, 125),
            _link("gamma-s09-s10", "sensor-09", "sensor-10", 0.92, 1.10, 6, 0.005, 250),
            _link("gamma-s10-s11", "sensor-10", "sensor-11", 0.89, 1.19, 8, 0.009, 250),
            _link("gamma-s11-s12", "sensor-11", "sensor-12", 0.86, 1.30, 10, 0.015, 250),
            # Cross-cluster links let the graph test multi-hop/alternative
            # paths beyond a sensor's own gateway cluster.
            _link("cross-s04-s05", "sensor-04", "sensor-05", 0.62, 2.40, 24, 0.07, 125),
            _link("cross-s08-s09", "sensor-08", "sensor-09", 0.64, 2.30, 23, 0.065, 125),
            _link("backbone-alpha-beta", "gateway-alpha", "gateway-beta", 0.99, 1.01, 2, 0.0, 10000),
            _link("backbone-beta-gamma", "gateway-beta", "gateway-gamma", 0.99, 1.01, 2, 0.0, 10000),
            _link("backbone-alpha-gamma", "gateway-alpha", "gateway-gamma", 0.83, 1.42, 18, 0.02, 1000),
        ],
    }


def _gateway(
    gateway_id: str, name: str, x: float, y: float, *, location: str
) -> dict[str, Any]:
    return {
        "gateway_id": gateway_id,
        "name": name,
        "position": {"x": x, "y": y, "location": location},
        "available": True,
        "transmission_range_m": 600.0,
        "local_storage": {"capacity_mb": 512.0, "used_mb": 12.0},
    }


def _sensor(
    node_id: str,
    name: str,
    gateway_id: str,
    x: float,
    y: float,
    battery_level: float,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "name": name,
        "gateway_id": gateway_id,
        "position": {"x": x, "y": y, "location": "field"},
        "available": True,
        "battery_level": battery_level,
        "transmission_range_m": 250.0,
        "data_source": "simulated_sensor",
    }


def _link(
    link_id: str,
    source: str,
    destination: str,
    quality: float,
    etx: float,
    latency_ms: float,
    packet_loss: float,
    bandwidth_kbps: float,
    *,
    bidirectional: bool = True,
) -> dict[str, Any]:
    return {
        "link_id": link_id,
        "source": source,
        "destination": destination,
        "quality": quality,
        "etx": etx,
        "latency_ms": latency_ms,
        "packet_loss": packet_loss,
        "bandwidth_kbps": bandwidth_kbps,
        "bidirectional": bidirectional,
        "available": True,
    }


def load_topology_config(path: str | Path) -> dict[str, Any]:
    """Load a topology JSON file and validate its high-level shape."""
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_topology_config(config)
    return config


def validate_topology_config(config: dict[str, Any]) -> None:
    for key in ("gateways", "sensors", "links"):
        if not isinstance(config.get(key), list):
            raise ValueError(  # noqa: TRY004 - config shape is a value error
                f"topology config needs a {key!r} list"
            )
    gateway_ids = {
        str(item["gateway_id"]) for item in config["gateways"] if item.get("gateway_id")
    }
    sensor_ids = {
        str(item["node_id"]) for item in config["sensors"] if item.get("node_id")
    }
    if gateway_ids & sensor_ids:
        raise ValueError("gateway and sensor ids must be distinct")
    known = gateway_ids | sensor_ids
    for sensor in config["sensors"]:
        assigned = sensor.get("gateway_id")
        if assigned is not None and assigned not in gateway_ids:
            raise ValueError(
                f"sensor {sensor.get('node_id')!r} references unknown gateway "
                f"{assigned!r}"
            )
    for link in config["links"]:
        for endpoint in (link.get("source"), link.get("destination")):
            if endpoint not in known:
                raise ValueError(f"link references unknown node {endpoint!r}")


def build_topology(config: dict[str, Any] | None = None) -> NetworkTopology:
    """Build a :class:`NetworkTopology` from a topology config dictionary."""
    resolved = config or default_topology_config()
    validate_topology_config(resolved)
    topology = NetworkTopology(name=str(resolved.get("name", "Simulated network")))
    topology.description = str(resolved.get("description", ""))

    for item in resolved["gateways"]:
        storage = item.get("local_storage") or {}
        gateway = GatewayNode(
            gateway_id=str(item["gateway_id"]),
            name=str(item.get("name", item["gateway_id"])),
            position=_position(item.get("position")),
            available=bool(item.get("available", True)),
            transmission_range_m=float(item.get("transmission_range_m", 600.0)),
            local_storage=LocalStorageStatus(
                capacity_mb=float(storage.get("capacity_mb", 512.0)),
                used_mb=float(storage.get("used_mb", 0.0)),
            ),
        )
        topology.add_gateway_node(gateway)

    for item in resolved["sensors"]:
        sensor = SensorNode(
            node_id=str(item["node_id"]),
            name=str(item.get("name", item["node_id"])),
            gateway_id=item.get("gateway_id"),
            position=_position(item.get("position")),
            available=bool(item.get("available", True)),
            battery_level=float(item.get("battery_level", 100.0)),
            transmission_range_m=float(item.get("transmission_range_m", 250.0)),
            data_source=str(item.get("data_source", "simulated_sensor")),
        )
        topology.add_sensor_node(sensor)

    for index, item in enumerate(resolved["links"]):
        source = str(item["source"])
        destination = str(item["destination"])
        link = NetworkLink(
            link_id=str(item.get("link_id", f"link-{index + 1}")),
            source=source,
            destination=destination,
            quality=float(item.get("quality", 1.0)),
            etx=float(item.get("etx", 1.0)),
            latency_ms=float(item.get("latency_ms", 10.0)),
            packet_loss=float(item.get("packet_loss", 0.0)),
            available=bool(item.get("available", True)),
            bandwidth_kbps=float(item.get("bandwidth_kbps", 250.0)),
            bidirectional=bool(item.get("bidirectional", True)),
        )
        topology.add_link(link)

    return topology


def _position(raw: Any) -> Position:
    if not isinstance(raw, dict):
        return Position()
    return Position(
        x=float(raw.get("x", 50.0)),
        y=float(raw.get("y", 35.0)),
        location=raw.get("location"),
    )


__all__ = [
    "build_topology",
    "default_topology_config",
    "load_topology_config",
    "validate_topology_config",
]
