"""Tests for the network simulator foundation (Stack 1)."""

from __future__ import annotations

import itertools

import pytest

from simulator.engine import NetworkSimulator, SimulationConfig
from simulator.entities import (
    GatewayNode,
    Position,
    SensorNode,
    SensorReading,
    utc_now_iso,
)
from simulator.links import NetworkLink
from simulator.sensor_data import SensorDataGenerator
from simulator.topology import NetworkTopology
from simulator.topology_config import build_topology, default_topology_config


def test_default_topology_has_three_gateways_and_twelve_sensors() -> None:
    topology = build_topology(default_topology_config())
    snapshot = topology.snapshot()
    assert snapshot["counts"]["gateways"] == 3
    assert snapshot["counts"]["sensors"] >= 10
    assert snapshot["counts"]["links"] >= 20
    gateway_ids = {node["node_id"] for node in snapshot["gateways"]}
    sensor_ids = {node["node_id"] for node in snapshot["sensors"]}
    assert gateway_ids.isdisjoint(sensor_ids)
    assert all(node["node_type"] == "gateway" for node in snapshot["gateways"])
    assert all(node["node_type"] == "sensor" for node in snapshot["sensors"])
    assigned = {
        node["gateway_id"]
        for node in snapshot["sensors"]
        if node["gateway_id"] is not None
    }
    assert assigned == gateway_ids
    for gateway in snapshot["gateways"]:
        assert gateway["connected_sensor_count"] >= 3
        assert "local_storage" in gateway
        assert "health" in gateway


def test_sensor_and_gateway_creation_and_removal() -> None:
    topology = NetworkTopology("test")
    gateway = topology.add_gateway_node(GatewayNode("gw-1", "Test gateway"))
    sensor = topology.add_sensor_node(
        SensorNode("sensor-a", "A", gateway_id="gw-1")
    )
    topology.add_link(NetworkLink("link-1", "gw-1", "sensor-a"))
    assert topology.get_gateway("gw-1") is gateway
    assert topology.get_sensor("sensor-a") is sensor
    assert sensor.neighbors == ["gw-1"]
    assert gateway.connected_sensor_count == 1

    with pytest.raises(ValueError, match="already exists"):
        topology.add_sensor_node(SensorNode("sensor-a", "duplicate"))

    removed = topology.remove_node("sensor-a")
    assert removed.node_id == "sensor-a"
    assert "sensor-a" not in topology.nodes
    assert "link-1" not in topology.links
    assert gateway.connected_sensor_count == 0

    topology.remove_node("gw-1")
    assert topology.nodes == {}


def test_gateway_removal_unassigns_sensors() -> None:
    topology = NetworkTopology("test")
    topology.add_gateway_node(GatewayNode("gw-1", "Gateway"))
    sensor = topology.add_sensor_node(SensorNode("s-1", "Sensor", gateway_id="gw-1"))
    assert sensor.gateway_id == "gw-1"
    topology.remove_node("gw-1")
    assert sensor.gateway_id is None


def test_link_creation_removal_and_directionality() -> None:
    topology = NetworkTopology("test")
    topology.add_gateway_node(GatewayNode("gw-1", "Gateway"))
    topology.add_sensor_node(SensorNode("s-1", "S1", gateway_id="gw-1"))
    topology.add_sensor_node(SensorNode("s-2", "S2", gateway_id="gw-1"))

    link = NetworkLink(
        "directed",
        "s-1",
        "s-2",
        quality=0.8,
        etx=1.4,
        latency_ms=12,
        packet_loss=0.02,
        bandwidth_kbps=125,
        bidirectional=False,
    )
    topology.add_link(link)
    assert topology.neighbors("s-1") == ["s-2"]
    assert topology.neighbors("s-2") == []
    assert topology.find_paths("s-1", "s-2", available_only=False) == [
        ["s-1", "s-2"]
    ]
    assert topology.find_paths("s-2", "s-1", available_only=False) == []

    removed = topology.remove_link("directed")
    assert removed.link_id == "directed"
    assert topology.neighbors("s-1") == []
    with pytest.raises(ValueError, match="unknown link"):
        topology.get_link("directed")


def test_default_topology_has_multihop_and_alternative_paths() -> None:
    topology = build_topology(default_topology_config())
    alpha_paths = topology.find_paths(
        "sensor-04", "gateway-01", max_paths=4
    )
    beta_paths = topology.find_paths("sensor-08", "gateway-02", max_paths=4)
    assert len(alpha_paths) >= 2
    assert len(beta_paths) >= 2
    assert any(len(path) > 2 for path in alpha_paths)
    assert any(len(path) > 2 for path in beta_paths)

    # The graph is not constrained to a sensor's own gateway cluster.
    cross_path = topology.shortest_path("sensor-04", "gateway-03")
    assert cross_path is not None
    assert "gateway-03" in cross_path


def test_sensor_readings_are_in_range_smooth_and_labelled_simulated() -> None:
    generator = SensorDataGenerator("sensor-01", seed=7)
    readings = [
        generator.generate(f"2026-01-01T00:{index:02d}:00.000Z")
        for index in range(180)
    ]
    assert all(reading.simulated for reading in readings)
    assert all(reading.to_dict()["label"] == "SIMULATED" for reading in readings)
    assert all(0 <= reading.pm25 <= 500 for reading in readings)
    assert all(0 <= reading.pm10 <= 600 for reading in readings)
    assert all(-10 <= reading.temperature_c <= 60 for reading in readings)
    assert all(0 <= reading.humidity_pct <= 100 for reading in readings)
    assert all(reading.pm10 >= reading.pm25 for reading in readings)

    pm25_steps = [
        abs(right.pm25 - left.pm25)
        for left, right in itertools.pairwise(readings)
    ]
    humidity_steps = [
        abs(right.humidity_pct - left.humidity_pct)
        for left, right in itertools.pairwise(readings)
    ]
    assert max(pm25_steps) < 25
    assert max(humidity_steps) < 10
    assert len({round(reading.pm25, 3) for reading in readings}) > 20


def test_sensor_reading_validation_rejects_out_of_range_values() -> None:
    with pytest.raises(ValueError, match="pm25"):
        SensorReading(
            timestamp=utc_now_iso(),
            pm25=501,
            pm10=200,
            temperature_c=20,
            humidity_pct=50,
        ).validate()
    with pytest.raises(ValueError, match="humidity"):
        SensorReading(
            timestamp=utc_now_iso(),
            pm25=20,
            pm10=30,
            temperature_c=20,
            humidity_pct=101,
        ).validate()


def test_simulator_start_stop_advance_and_readings() -> None:
    engine = NetworkSimulator()
    assert engine.running is False
    assert engine.status_payload()["state"] == "stopped"

    started = engine.start()
    assert started["running"] is True
    assert engine.running is True
    first_reading_total = started["reading_total"]
    assert first_reading_total == 12

    engine.advance(12)
    status = engine.status_payload()
    assert status["running"] is True
    assert status["reading_total"] > first_reading_total
    sensors = engine.sensors_payload()
    assert all(node["latest_reading"] is not None for node in sensors)
    assert all(node["latest_reading"]["simulated"] for node in sensors)
    assert all(node["reading_count"] >= 3 for node in sensors)

    stopped = engine.stop()
    assert stopped["running"] is False
    assert stopped["state"] == "stopped"
    assert engine.running is False


def test_simulator_can_create_remove_and_reset_nodes_and_links() -> None:
    engine = NetworkSimulator()
    gateway = engine.create_gateway_node(
        gateway_id="gateway-delta", name="Delta", position=Position(10, 10)
    )
    assert gateway["node_type"] == "gateway"
    sensor = engine.create_sensor_node(
        node_id="sensor-99",
        name="Extra sensor",
        gateway_id="gateway-delta",
        battery_level=55,
    )
    assert sensor["gateway_id"] == "gateway-delta"
    assert sensor["battery_level"] == 55

    link = engine.create_link(
        source="sensor-99",
        destination="gateway-delta",
        link_id="extra-link",
        quality=0.7,
        etx=1.6,
    )
    assert link["link_id"] == "extra-link"
    assert link["bidirectional"] is True
    assert "gateway-delta" in engine.topology.neighbors("sensor-99")

    engine.remove_link("extra-link")
    assert "extra-link" not in {item["link_id"] for item in engine.links_payload()}

    engine.remove_node("sensor-99")
    assert "sensor-99" not in {item["node_id"] for item in engine.nodes_payload()}

    engine.start()
    engine.advance(10)
    assert engine.status_payload()["reading_total"] > 0
    reset = engine.reset()
    assert reset["running"] is False
    assert reset["reading_total"] == 0
    assert reset["counts"]["sensors"] == 12
    assert "gateway-delta" not in {
        item["node_id"] for item in engine.nodes_payload()
    }


def test_simulation_config_rejects_invalid_intervals() -> None:
    with pytest.raises(ValueError, match="interval_seconds"):
        SimulationConfig(interval_seconds=0)
    with pytest.raises(ValueError, match="history_limit"):
        SimulationConfig(history_limit=0)


def test_snapshot_shape_contains_simulation_and_topology() -> None:
    engine = NetworkSimulator()
    snapshot = engine.snapshot()
    assert {"simulation", "topology", "fl_clients"} <= set(snapshot)
    assert snapshot["simulation"]["note"].startswith("Simulated network only")
    assert snapshot["topology"]["counts"]["sensors"] == 12
    assert snapshot["topology"]["gateway_assignments"]
    assert snapshot["topology"]["links"][0]["etx"] >= 1
