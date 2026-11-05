"""Unit tests for the offline registry loader and pooled metrics."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from baselines.common import evaluate_targets
from server.offline_eval import OfflineEvalError, pooled_metrics, resolve_registry


def _write_record(
    directory: Path, version: str, *, round_number: int, val_loss: float
) -> None:
    record = {
        "model_version": version,
        "round": round_number,
        "weighted_val_loss": val_loss,
        "model": {"window_hours": 24, "n_features": 5, "pool_size": 1},
    }
    (directory / f"global_{version}.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    np.save(directory / f"global_{version}.npy", np.zeros(4, dtype=np.float32))


def test_resolve_registry_prefers_latest_then_best_and_allows_explicit_version(
    tmp_path: Path,
) -> None:
    _write_record(tmp_path, "v0001", round_number=1, val_loss=0.5)
    _write_record(tmp_path, "v0002", round_number=2, val_loss=0.8)
    (tmp_path / "latest.json").write_text(
        (tmp_path / "global_v0002.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "best.json").write_text(
        (tmp_path / "global_v0001.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    record, path = resolve_registry(tmp_path)
    assert record["model_version"] == "v0002"
    assert path.name == "global_v0002.npy"

    record, path = resolve_registry(tmp_path, prefer_best=True)
    assert record["model_version"] == "v0001"
    assert path.name == "global_v0001.npy"

    record, path = resolve_registry(tmp_path, version="v0002")
    assert record["model_version"] == "v0002"
    assert path.name == "global_v0002.npy"

    with pytest.raises(OfflineEvalError, match="not found"):
        resolve_registry(tmp_path, version="v0009")


def test_resolve_registry_requires_the_requested_pointer(tmp_path: Path) -> None:
    record = {"model_version": "v0001", "model": {"window_hours": 24}}
    (tmp_path / "best.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(OfflineEvalError, match="no latest.json"):
        resolve_registry(tmp_path)


def test_resolve_registry_rejects_a_missing_weight_file(tmp_path: Path) -> None:
    record = {"model_version": "v0001", "model": {"window_hours": 24}}
    (tmp_path / "latest.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(OfflineEvalError, match="weights not found"):
        resolve_registry(tmp_path)


def test_pooled_metrics_concatenates_node_test_slices() -> None:
    prepared = {
        "node1": {
            "y_test_raw": np.array([1.0, 2.0]),
            "y_test_clipped": np.array([1.0, 2.0]),
        },
        "node2": {
            "y_test_raw": np.array([3.0, 4.0, 5.0]),
            "y_test_clipped": np.array([2.5, 4.0, 5.0]),
        },
    }
    predictions = {
        "node1": np.array([1.5, 1.5]),
        "node2": np.array([2.0, 4.0, 6.0]),
    }

    result = pooled_metrics(predictions, prepared)

    assert result["nodes"] == ["node1", "node2"]
    assert result["n_test"] == 5
    expected = evaluate_targets(
        np.array([1.5, 1.5, 2.0, 4.0, 6.0]),
        np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        np.array([1.0, 2.0, 2.5, 4.0, 5.0]),
    )
    assert result["metrics"] == pytest.approx(expected)


def test_pooled_metrics_requires_every_prepared_node() -> None:
    with pytest.raises(ValueError, match="missing prepared data"):
        pooled_metrics({"node1": np.zeros(2)}, {})
