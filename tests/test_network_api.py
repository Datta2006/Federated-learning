"""API tests for the ``/api/network`` namespace."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from dashboard.backend.main import create_app
from dashboard.backend.settings import Settings


def _client(tmp_path: Path) -> TestClient:
    dataset = tmp_path / "data.csv"
    dataset.write_text(
        "No,year,month,day,hour,pm2.5,DEWP,TEMP,PRES,cbwd,Iws,Is,Ir\n"
        "1,2014,1,1,0,10,-5,-2,1020,NW,1.0,0,0\n",
        encoding="utf-8",
    )
    settings = replace(
        Settings.load(),
        mqtt_enabled=False,
        registry_dir=None,
        registry_source="unavailable",
        dataset_path=dataset,
        predictions_path=tmp_path / "missing_predictions.json",
    )
    return TestClient(create_app(settings))


def test_network_read_endpoints(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        topology = client.get("/api/network/topology")
        assert topology.status_code == 200
        body = topology.json()
        assert body["topology"]["counts"]["gateways"] == 3
        assert body["topology"]["counts"]["sensors"] == 12
        assert body["simulation"]["running"] is False

        nodes = client.get("/api/network/nodes").json()
        assert nodes["count"] == 15
        gateways = client.get("/api/network/gateways").json()
        assert gateways["count"] == 3
        links = client.get("/api/network/links").json()
        assert links["count"] >= 20
        assert all("etx" in link for link in links["links"])

        status = client.get("/api/network/status").json()
        assert status["counts"]["sensors"] == 12
        assert status["config"]["interval_seconds"] > 0

        config = client.get("/api/network/config").json()
        assert config["topology"]["name"]
        assert config["ranges"]["pm25"] == [0, 500]
        assert config["ranges"]["pm10"] == [0, 600]


def test_network_simulation_start_advance_stop_and_reset(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        start = client.post("/api/network/simulation/start")
        assert start.status_code == 200
        assert start.json()["simulation"]["running"] is True
        assert start.json()["simulation"]["reading_total"] > 0

        advance = client.post(
            "/api/network/simulation/advance", json={"seconds": 15}
        )
        assert advance.status_code == 200
        simulation = advance.json()["simulation"]
        assert simulation["running"] is True
        assert simulation["reading_total"] > 12
        assert simulation["tick_count"] >= 1

        readings = client.get("/api/network/readings/sensor-01?limit=5")
        assert readings.status_code == 200
        payload = readings.json()
        assert payload["simulated"] is True
        assert payload["count"] >= 4
        assert all(row["simulated"] for row in payload["readings"])

        stop = client.post("/api/network/simulation/stop")
        assert stop.status_code == 200
        assert stop.json()["simulation"]["running"] is False

        reset = client.post("/api/network/simulation/reset")
        assert reset.status_code == 200
        reset_body = reset.json()["simulation"]
        assert reset_body["running"] is False
        assert reset_body["reading_total"] == 0
        assert reset_body["counts"]["sensors"] == 12


def test_network_node_link_crud(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        gateway = client.post(
            "/api/network/gateways",
            json={
                "gateway_id": "gateway-delta",
                "name": "Delta gateway",
                "position": {"x": 12, "y": 15},
            },
        )
        assert gateway.status_code == 200, gateway.text
        assert gateway.json()["gateway"]["node_type"] == "gateway"

        sensor = client.post(
            "/api/network/nodes",
            json={
                "node_id": "sensor-99",
                "name": "New sensor",
                "gateway_id": "gateway-delta",
                "battery_level": 64,
                "position": {"x": 14, "y": 32},
            },
        )
        assert sensor.status_code == 200, sensor.text
        assert sensor.json()["node"]["node_type"] == "sensor"

        link = client.post(
            "/api/network/links",
            json={
                "source": "sensor-99",
                "destination": "gateway-delta",
                "link_id": "link-99",
                "quality": 0.75,
                "etx": 1.5,
                "bidirectional": False,
            },
        )
        assert link.status_code == 200, link.text
        assert link.json()["link"]["direction"] == "directional"

        availability = client.post(
            "/api/network/nodes/sensor-99/availability",
            json={"available": False},
        )
        assert availability.status_code == 200
        assert availability.json()["node"]["available"] is False

        duplicate = client.post(
            "/api/network/nodes",
            json={"node_id": "sensor-99", "name": "Duplicate"},
        )
        assert duplicate.status_code == 400

        delete_link = client.delete("/api/network/links/link-99")
        assert delete_link.status_code == 200
        delete_sensor = client.delete("/api/network/nodes/sensor-99")
        assert delete_sensor.status_code == 200
        assert delete_sensor.json()["node"]["node_id"] == "sensor-99"

        delete_gateway = client.delete("/api/network/gateways/gateway-delta")
        assert delete_gateway.status_code == 200


def test_existing_dashboard_endpoints_still_work_with_network_router(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        for path in (
            "/api/health",
            "/api/status",
            "/api/workers",
            "/api/network/topology",
        ):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
