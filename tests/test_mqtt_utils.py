"""Unit tests for MQTT topic and JSON message helpers."""

import pytest

from common.mqtt_utils import dumps, loads, make_message, node_topic
from node.node_client import make_health, make_status


def test_node_topic_builds_stage2_topics():
    assert node_topic("aq", "node1", "status") == "aq/node1/status"
    assert node_topic("/aq/", "/node2/", "/health/") == "aq/node2/health"


def test_node_topic_rejects_embedded_slashes():
    with pytest.raises(ValueError, match="must not contain slashes"):
        node_topic("aq", "node1/bad", "status")


def test_make_message_adds_schema_node_and_timestamp():
    message = make_message("node1", state="online")

    assert message["schema_version"] == 1
    assert message["node_id"] == "node1"
    assert message["state"] == "online"
    assert message["ts"].endswith("Z")


def test_json_round_trip_preserves_payload():
    message = make_message("node1", state="offline", reason="lwt")

    assert loads(dumps(message)) == message


def test_status_and_health_payloads_do_not_fabricate_sensor_data():
    status = make_status("node1", "offline", "lwt")
    health = make_health("node1", backend="none", uptime_sec=12.34)

    assert status["state"] == "offline"
    assert status["reason"] == "lwt"
    assert health["backend"] == "none"
    assert health["uptime_sec"] == 12.3
    assert health["battery_pct"] is None
    assert health["rssi_dbm"] is None
    assert health["cpu_temp_c"] is None
    assert health["last_read_age_sec"] is None
