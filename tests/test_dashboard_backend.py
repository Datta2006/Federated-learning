"""Tests for the AirFed dashboard's file parsing and MQTT state machine."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from dashboard.backend.air_quality import AirQualityReader, parse_dataset_rows
from dashboard.backend.metrics import build_metrics, parse_results_csv
from dashboard.backend.registry import RegistryReader, parse_round_rows
from dashboard.backend.settings import PROJECT_ROOT, Settings
from dashboard.backend.telemetry import TelemetryStore

ROUNDS_CSV = """round,selected,received,dropped_nodes,bytes_up,bytes_down,round_time_sec,weighted_val_loss,evaluated_version,model_version
1,node1 node2 node3 node4,4,,198365,100552,5.209,0.05955523238087349,v0000,v0001
2,node1 node2 node3,3,node4,149000,100553,6.028,,v0001,v0002
"""


def _write_registry(tmp_path: Path) -> Path:
    registry = tmp_path / "registry"
    registry.mkdir()
    latest = {
        "model_version": "v0002",
        "round": 2,
        "created_utc": "2026-11-05T12:00:00Z",
        "parameters": 9025,
        "weighted_val_loss": None,
        "n_samples": 18000,
        "n_val": 0,
        "sources": ["node1", "node2"],
        "kind": "model",
        "model": {"architecture": "cnn_rnn_improved", "window_hours": 24},
    }
    best = {**latest, "model_version": "v0001", "round": 1, "weighted_val_loss": 0.02}
    (registry / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    (registry / "best.json").write_text(json.dumps(best), encoding="utf-8")
    (registry / "global_v0002.json").write_text(json.dumps(latest), encoding="utf-8")
    (registry / "global_v0001.json").write_text(json.dumps(best), encoding="utf-8")
    (registry / "global_v0002.npy").write_bytes(b"weights")
    (registry / "rounds.csv").write_text(ROUNDS_CSV, encoding="utf-8")
    return registry


def _store() -> TelemetryStore:
    return TelemetryStore(
        nodes={"node1": 2010, "node2": 2011, "node3": 2012, "node4": 2013, "node5": 2014},
        training_nodes={"node1", "node2", "node3", "node4"},
        inference_nodes={"node5"},
        base_topic="aq",
        heartbeat_sec=10,
        stale_after_sec=30,
        round_stale_after_sec=120,
    )


def _meta(round_number: int, node_id: str) -> dict:
    return {
        "schema_version": 1,
        "node_id": node_id,
        "ts": "2026-11-05T12:00:00.000Z",
        "message_type": "update_meta",
        "round": round_number,
        "model_version": "v0008",
        "n_samples": 6286,
        "n_val": 698,
        "val_loss": 0.0024,
        "chunks": 1,
        "sha256": "a" * 64,
    }


def _chunk(round_number: int, node_id: str, data: bytes) -> dict:
    return {
        "schema_version": 1,
        "node_id": node_id,
        "ts": "2026-11-05T12:00:00.000Z",
        "message_type": "chunk",
        "round": round_number,
        "model_version": "v0008",
        "index": 0,
        "chunks": 1,
        "size": len(data),
        "data": base64.b64encode(data).decode("ascii"),
        "chunk_sha256": hashlib.sha256(data).hexdigest(),
    }


def test_parse_round_rows_normalizes_types() -> None:
    rows = parse_round_rows(ROUNDS_CSV)
    assert len(rows) == 2
    assert rows[0]["round"] == 1
    assert rows[0]["selected"] == ["node1", "node2", "node3", "node4"]
    assert rows[0]["received"] == 4
    assert rows[0]["bytes_up"] == 198365
    assert rows[0]["weighted_val_loss"] == pytest.approx(0.05955523238087349)
    assert rows[1]["dropped_nodes"] == ["node4"]
    assert rows[1]["weighted_val_loss"] is None


def test_registry_reader_uses_existing_records(tmp_path: Path) -> None:
    registry = _write_registry(tmp_path)
    reader = RegistryReader(registry, source="test")
    snapshot = reader.snapshot()
    assert snapshot["available"] is True
    assert snapshot["current_round"] == 2
    assert snapshot["latest"]["model_version"] == "v0002"
    assert snapshot["best"]["model_version"] == "v0001"
    assert snapshot["latest_model_bytes"] == 9025 * 4
    assert snapshot["chunk_count"] == 3
    assert [item["model_version"] for item in snapshot["versions"]] == [
        "v0002",
        "v0001",
    ]


def test_results_parser_and_comparison() -> None:
    text = (PROJECT_ROOT / "results.csv").read_text(encoding="utf-8")
    rows = parse_results_csv(text)
    assert len(rows) >= 10
    metrics = build_metrics(
        results_path=PROJECT_ROOT / "results.csv",
        seed_path=PROJECT_ROOT / "results_by_seed.csv",
        summary_path=PROJECT_ROOT / "stage4_summary.json",
        rounds=parse_round_rows(ROUNDS_CSV),
    )
    comparison = metrics["comparison"]
    assert [row["short"] for row in comparison] == [
        "Persistence",
        "Local-only",
        "Centralized",
        "FedAvg",
    ]
    assert metrics["loss_history"][0]["round"] == 1
    assert metrics["loss_history"][1]["available"] is False


def test_telemetry_round_lifecycle_and_checksums() -> None:
    store = _store()
    store.set_broker_state(True, now=100.0)
    store.ingest(
        "aq/node1/status",
        {"schema_version": 1, "state": "online", "ts": "2026-11-05T12:00:00Z"},
        now=101.0,
    )
    store.ingest(
        "aq/node1/health",
        {"schema_version": 1, "backend": "replay", "uptime_sec": 3},
        now=102.0,
    )
    store.ingest(
        "aq/fl/round/9/start",
        {
            "schema_version": 1,
            "ts": "2026-11-05T12:00:00Z",
            "message_type": "round_start",
            "round": 9,
            "model_version": "v0008",
            "selected_nodes": ["node1", "node2"],
        },
        now=103.0,
    )
    store.ingest(
        "aq/fl/round/9/update/node1/meta",
        _meta(9, "node1"),
        now=104.0,
    )
    store.ingest(
        "aq/fl/round/9/update/node1/chunk/0",
        _chunk(9, "node1", b"model-weights"),
        now=105.0,
    )
    store.ingest(
        "aq/fl/round/9/ack/node1",
        {"schema_version": 1, "status": "accepted", "reason": None, "model_version": "v0008"},
        now=106.0,
    )
    store.ingest(
        "aq/fl/round/9/ack/node2",
        {"schema_version": 1, "status": "rejected", "reason": "checksum mismatch"},
        now=107.0,
    )

    snapshot = store.status_payload({"available": False, "rounds": []}, now=108.0)
    assert snapshot["nodes"][0]["status"] == "online"
    current = snapshot["current_round"]
    assert current["round"] == 9
    assert current["phase"] == "aggregating"
    assert current["received"] == 1
    assert current["acks"] == {"node1": "accepted", "node2": "rejected"}
    assert current["reasons"]["node2"] == "checksum mismatch"
    stages = {item["key"]: item["status"] for item in current["stages"]}
    assert stages["model_broadcast"] == "complete"
    assert stages["weight_upload"] == "complete"
    assert stages["fedavg_aggregation"] == "active"
    assert store.communication_payload({"available": False})["observed"][
        "checksum_ok"
    ] == 1

    store.ingest(
        "aq/fl/global/announce",
        {
            "schema_version": 1,
            "message_type": "announce",
            "model_version": "v0009",
            "federated_round": 9,
            "chunks": 1,
            "sha256": "b" * 64,
        },
        now=109.0,
    )
    snapshot = store.status_payload({"available": False, "rounds": []}, now=110.0)
    assert snapshot["current_round"]["phase"] == "completed"
    assert snapshot["current_round"]["registered_version"] == "v0009"


def test_telemetry_rejects_bad_chunk_checksum() -> None:
    store = _store()
    chunk = _chunk(9, "node1", b"payload")
    chunk["chunk_sha256"] = "0" * 64
    store.ingest("aq/fl/round/9/start", {"round": 9, "selected_nodes": ["node1"]})
    event = store.ingest(
        "aq/fl/round/9/update/node1/chunk/0", chunk
    )
    assert event is not None
    assert event["checksum_ok"] is False
    assert store.communication_payload({"available": False})["observed"][
        "checksum_bad"
    ] == 1


def test_historical_round_fallback() -> None:
    store = _store()
    registry = {
        "available": True,
        "latest": {"model_version": "v0002"},
        "rounds": parse_round_rows(ROUNDS_CSV),
    }
    snapshot = store.status_payload(registry, now=100.0)
    assert snapshot["current_round"]["source"] == "registry"
    assert snapshot["current_round"]["round"] == 2
    assert snapshot["round_is_live"] is False


def _dataset_text() -> str:
    lines = ["No,year,month,day,hour,pm2.5,DEWP,TEMP,PRES,cbwd,Iws,Is,Ir"]
    values = [None, 10.0, 30.0, 20.0]
    for index, value in enumerate(values):
        lines.append(
            f"{index + 1},2014,1,1,{index},{'NA' if value is None else value},"
            "-5,-2,1020,NW,1.0,0,0"
        )
    return "\n".join(lines) + "\n"


def _predictions() -> dict:
    return {
        "model_version": "v0015",
        "horizon_hours": 1,
        "nodes": {
            "node5": {
                "timestamps": [
                    "2014-01-01T00:00:00",
                    "2014-01-01T01:00:00",
                    "2014-01-01T02:00:00",
                ],
                "actual": [10.0, None, 30.0],
                "actual_filled": [10.0, 10.0, 30.0],
                "predicted": [11.0, 12.0, 33.0],
            }
        },
    }


def test_air_quality_merges_model_predictions_and_weather(tmp_path: Path) -> None:
    dataset = tmp_path / "data.csv"
    dataset.write_text(_dataset_text(), encoding="utf-8")
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(_predictions()), encoding="utf-8")
    reader = AirQualityReader(dataset, predictions, nodes={"node5": 2014})
    payload = reader.series("node5", limit=240, latest_model_version="v0015")
    assert payload["prediction_source"] == "fedavg_offline"
    assert payload["is_realtime"] is False
    assert payload["prediction_stale"] is False
    assert payload["series"][0]["predicted"] == 11.0
    assert payload["series"][0]["temp"] == -2.0
    assert payload["series"][0]["rh"] is not None


def test_air_quality_persistence_fallback_is_explicit(tmp_path: Path) -> None:
    dataset = tmp_path / "data.csv"
    dataset.write_text(_dataset_text(), encoding="utf-8")
    reader = AirQualityReader(dataset, tmp_path / "missing.json", nodes={"node5": 2014})
    payload = reader.series("node5", limit=240, latest_model_version="v0015")
    assert payload["prediction_source"] == "persistence_reference"
    assert "not model output" in payload["prediction_label"]
    assert payload["series"][0]["predicted"] == 10.0
    assert "not live telemetry" in payload["actual_note"]


def test_dataset_parser_fills_leading_gap() -> None:
    rows = parse_dataset_rows(_dataset_text())
    assert rows[0]["pm25"] is None
    assert rows[1]["pm25"] == 10.0
    assert rows[0]["pm25_filled"] == 10.0
    assert rows[1]["pm25_filled"] == 10.0
    assert rows[2]["pm25_filled"] == 30.0


def test_api_endpoints_and_websocket(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from dashboard.backend.main import create_app

    registry = _write_registry(tmp_path)
    dataset = tmp_path / "data.csv"
    dataset.write_text(_dataset_text(), encoding="utf-8")
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(_predictions()), encoding="utf-8")

    settings = replace(
        Settings.load(),
        mqtt_enabled=False,
        registry_dir=registry,
        registry_source="test",
        dataset_path=dataset,
        predictions_path=predictions,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        for path in [
            "/api/health",
            "/api/status",
            "/api/rounds",
            "/api/model",
            "/api/metrics",
            "/api/air-quality?node=node5",
            "/api/communication",
        ]:
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
        status = client.get("/api/status").json()
        assert status["registry"]["source"] == "test"
        assert status["latest_model"]["model_version"] == "v0002"
        rounds = client.get("/api/rounds").json()
        assert rounds["round_count"] == 2
        air = client.get("/api/air-quality?node=node5").json()
        assert air["prediction_source"] == "fedavg_offline"
        with client.websocket_connect("/ws") as websocket:
            hello = websocket.receive_json()
            assert hello["type"] == "hello"
