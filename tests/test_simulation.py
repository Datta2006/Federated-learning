"""Unit tests for dynamic simulation sharding over training years only."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from common.simulation import (
    build_shard_plan,
    prepare_simulation_shard,
    training_years,
)

NODES = {
    "node1": 2010,
    "node2": 2011,
    "node3": 2012,
    "node4": 2013,
    "node5": 2014,
}


def _config(**overrides):
    config = {
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
    config.update(overrides)
    return config


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


def test_training_years_excludes_inference_year() -> None:
    assert training_years(_config()) == [2010, 2011, 2012, 2013]


def test_training_years_honours_explicit_subset() -> None:
    config = _config()
    config["federated"]["simulation_years"] = [2011, 2012]
    assert training_years(config) == [2011, 2012]


@pytest.mark.parametrize("workers", [1, 2, 4, 10, 100])
def test_shard_plan_is_complete_disjoint_and_training_only(workers: int) -> None:
    raw = _raw()
    config = _config()
    plan = build_shard_plan(config, raw, n_workers=workers)

    assert len(plan) == workers
    assert {item.shard_index for item in plan} == set(range(workers))
    assert all(item.shard_count == workers for item in plan)
    assert 2014 not in {item.year for item in plan}

    train_length = int(60 * 0.8)
    covered_years = {item.year for item in plan}
    assert covered_years, "the plan must use at least one training year"
    assert covered_years <= {2010, 2011, 2012, 2013}
    for year in covered_years:
        year_parts = sorted(
            (item for item in plan if item.year == year), key=lambda item: item.start_row
        )
        assert year_parts, f"year {year} received no shard"
        assert year_parts[0].start_row == 0
        assert year_parts[-1].end_row == train_length
        for left, right in itertools.pairwise(year_parts):
            assert left.end_row == right.start_row, "shards must be contiguous"
        assert sum(item.train_rows for item in year_parts) == train_length
        for item in year_parts:
            assert item.start_row < item.end_row <= train_length


def test_prepared_shards_are_ordered_and_never_share_windows() -> None:
    raw = _raw()
    config = _config()
    shards = [
        prepare_simulation_shard(
            raw, config, n_workers=2, shard_index=index, window_hours=24
        )
        for index in range(2)
    ]

    all_train: list[pd.Timestamp] = []
    all_val: list[pd.Timestamp] = []
    for shard in shards:
        prepared = shard["prepared"]
        assert shard["dataset"] == "simulation"
        assert shard["n_samples"] > 0
        assert shard["n_val"] > 0
        assert prepared["X_test"].shape[0] == 0
        assert prepared["X_train"].shape[1] == 24
        assert prepared["X_train"].shape[2] == prepared["n_features"]
        assert np.isfinite(prepared["X_train"]).all()
        train_ts = [pd.Timestamp(value) for value in prepared["train_timestamps"]]
        val_ts = [pd.Timestamp(value) for value in prepared["val_timestamps"]]
        assert train_ts == sorted(train_ts), "temporal order must be preserved"
        assert val_ts == sorted(val_ts)
        assert train_ts[-1] < val_ts[0], "validation follows training in time"
        assert all(ts.year == shard["year"] for ts in train_ts + val_ts)
        # No shard may reach into the held-out test tail of its year.
        year_start = pd.Timestamp(f"{shard['year']}-01-01")
        train_end = year_start + pd.Timedelta(hours=int(60 * 0.8) - 1)
        assert max(train_ts + val_ts) <= train_end
        all_train.extend(train_ts)
        all_val.extend(val_ts)

    assert len(set(all_train)) == len(all_train), "training windows overlap"
    assert len(set(all_val)) == len(all_val), "validation windows overlap"
    assert not set(all_train) & set(all_val)


def test_shard_count_validation() -> None:
    raw = _raw()
    with pytest.raises(ValueError):
        build_shard_plan(_config(), raw, n_workers=0)
    with pytest.raises(ValueError):
        prepare_simulation_shard(raw, _config(), n_workers=2, shard_index=2)
