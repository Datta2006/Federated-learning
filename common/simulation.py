"""Dynamic simulation shards over the *training* portion of the dataset.

The original deployment gave every worker one whole year.  That does not scale
to ten or a hundred workers: workers would duplicate data and a single process
would own thousands of samples while others owned none.

This module partitions only the configured training years (2010-2013 by
default) into contiguous, non-overlapping shards.  Every shard is built from
its own rows, in timestamp order, and the held-out tail of each year is never
touched.  No worker receives a copy of the full dataset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from common.preprocess import clean_pm25_series, fill_pm25_series, minmax_scale


@dataclass(frozen=True)
class ShardPlan:
    """One contiguous slice of one training year."""

    year: int
    shard_index: int
    shard_count: int
    start_row: int
    end_row: int
    train_rows: int


def training_years(config: dict[str, Any]) -> list[int]:
    """Return the years that may be used for simulated training.

    Inference-only node years (e.g. 2014) are excluded because the project
    keeps them as unseen test data.  ``federated.simulation_years`` can pin an
    explicit subset.
    """
    federated = config.get("federated", {})
    nodes = {
        str(node_id): int(year)
        for node_id, year in dict(config.get("nodes", {})).items()
    }
    inference = set(federated.get("inference_only_nodes") or [])
    inference_years = {nodes[node] for node in inference if node in nodes}

    configured = federated.get("simulation_years")
    if configured:
        years = [int(year) for year in configured]
    else:
        years = sorted(set(nodes.values()))
    years = [year for year in years if year not in inference_years]
    if not years:
        raise ValueError(
            "no training years are available for simulation; check "
            "federated.training_nodes/inference_only_nodes"
        )
    return years


def _year_train_frame(
    raw: pd.DataFrame, year: int, train_fraction: float
) -> pd.DataFrame:
    frame = (
        raw.loc[raw["year"] == year]
        .sort_values("timestamp")
        .copy()
        .reset_index(drop=True)
    )
    if frame.empty:
        raise ValueError(f"no rows for training year {year}")
    split_row = int(len(frame) * train_fraction)
    if split_row < 2 or split_row >= len(frame):
        raise ValueError(
            f"year {year} cannot be split at {train_fraction:.2f} for simulation"
        )
    # Only the leading training portion; the test tail is never included.
    return frame.iloc[:split_row].reset_index(drop=True)


def build_shard_plan(
    config: dict[str, Any],
    raw: pd.DataFrame,
    *,
    n_workers: int,
) -> list[ShardPlan]:
    """Split the pooled training rows into ``n_workers`` contiguous shards."""
    if n_workers < 1:
        raise ValueError("n_workers must be at least 1")
    train_fraction = float(config.get("train_fraction", 0.8))
    years = training_years(config)
    frames = {year: _year_train_frame(raw, year, train_fraction) for year in years}

    total_rows = sum(len(frame) for frame in frames.values())
    if total_rows < n_workers:
        raise ValueError(
            f"{n_workers} workers need at least {n_workers} training rows; "
            f"only {total_rows} are available"
        )

    # Allocate shards proportionally, giving every selected year at least one
    # shard while keeping the total exactly n_workers.
    weights = {year: len(frame) for year, frame in frames.items()}
    allocations: dict[int, int] = {}
    if n_workers >= len(years):
        for year in years:
            allocations[year] = 1
        remaining = n_workers - len(years)
        order = sorted(years, key=lambda year: weights[year], reverse=True)
        for offset in range(remaining):
            allocations[order[offset % len(order)]] += 1
    else:
        order = sorted(years, key=lambda year: weights[year], reverse=True)
        for year in order[:n_workers]:
            allocations[year] = 1

    plan: list[ShardPlan] = []
    shard_index = 0
    for year in sorted(allocations):
        count = allocations[year]
        frame = frames[year]
        # np.linspace gives contiguous, non-overlapping boundaries that cover
        # the training rows exactly once.
        boundaries = np.linspace(0, len(frame), count + 1, dtype=int)
        for part in range(count):
            start = int(boundaries[part])
            end = int(boundaries[part + 1])
            if end <= start:
                raise ValueError(
                    f"year {year} produced an empty shard for {n_workers} workers"
                )
            plan.append(
                ShardPlan(
                    year=year,
                    shard_index=shard_index,
                    shard_count=n_workers,
                    start_row=start,
                    end_row=end,
                    train_rows=end - start,
                )
            )
            shard_index += 1
    return plan


def _prepare_shard(
    year_frame: pd.DataFrame,
    *,
    config: dict[str, Any],
    window_hours: int,
    horizon: int,
    train_fraction_of_windows: float,
) -> dict[str, Any]:
    """Scale and window one contiguous shard without crossing its boundary."""
    scaler = config["scaler"]
    features = list(config.get("features", ["pm25", "temp", "rh"]))
    clip_value = float(scaler["pm25_clip"])

    frame = year_frame.copy().reset_index(drop=True)
    frame["pm25_raw"] = fill_pm25_series(frame["pm2.5"])
    frame["pm25"] = clean_pm25_series(frame["pm2.5"], clip_value)

    feature_min = np.asarray(scaler["feature_min"], dtype=np.float32)
    feature_max = np.asarray(scaler["feature_max"], dtype=np.float32)
    scaled = minmax_scale(
        frame[features].to_numpy(dtype=np.float32), feature_min, feature_max
    )
    pm25_index = features.index("pm25")
    pm25_scaled = scaled[:, pm25_index].astype(np.float32, copy=True)
    pm25_min = float(feature_min[pm25_index])
    pm25_max = float(feature_max[pm25_index])

    hours = frame["timestamp"].dt.hour.to_numpy(dtype=np.float32)
    angle = 2.0 * np.pi * hours / 24.0
    scaled = np.hstack(
        [scaled, np.sin(angle)[:, None], np.cos(angle)[:, None]]
    ).astype(np.float32, copy=False)

    target_scaled = minmax_scale(
        frame["pm25"].to_numpy(dtype=np.float32).reshape(-1, 1),
        np.asarray([pm25_min], dtype=np.float32),
        np.asarray([pm25_max], dtype=np.float32),
    ).reshape(-1)
    raw_targets = frame["pm25_raw"].to_numpy(dtype=np.float32)
    clipped_targets = frame["pm25"].to_numpy(dtype=np.float32)
    timestamps = frame["timestamp"].to_numpy()

    sample_count = len(scaled) - window_hours - horizon + 1
    if sample_count < 3:
        raise ValueError(
            "a simulation shard is too short for "
            f"window_hours={window_hours} (rows={len(scaled)})"
        )
    starts = np.arange(sample_count, dtype=int)
    target_indices = starts + window_hours - 1 + horizon
    current_indices = starts + window_hours - 1
    X = np.stack(
        [scaled[start : start + window_hours] for start in starts]
    ).astype(np.float32)
    y = (target_scaled[target_indices] - pm25_scaled[current_indices]).astype(
        np.float32
    )

    val_count = round(sample_count * train_fraction_of_windows)
    val_count = max(val_count, 1)
    train_end = sample_count - val_count
    if train_end < 1:
        raise ValueError("a simulation shard has no training windows after validation")
    train_idx = np.arange(0, train_end, dtype=int)
    val_idx = np.arange(train_end, sample_count, dtype=int)

    return {
        "window_hours": int(window_hours),
        "horizon": int(horizon),
        "delta": True,
        "cyclic_hour": True,
        "n_features": int(scaled.shape[1]),
        "X_train": X[train_idx],
        "y_train": y[train_idx],
        "X_val": X[val_idx],
        "y_val": y[val_idx],
        "X_test": np.empty((0, window_hours, scaled.shape[1]), dtype=np.float32),
        "y_test": np.empty((0,), dtype=np.float32),
        "y_test_raw": np.empty((0,), dtype=np.float32),
        "y_test_clipped": np.empty((0,), dtype=np.float32),
        "current_test_pm25_raw": np.empty((0,), dtype=np.float32),
        "current_test_pm25_clipped": np.empty((0,), dtype=np.float32),
        "current_test_scaled": np.empty((0,), dtype=np.float32),
        "test_timestamps": np.empty((0,), dtype="datetime64[ns]"),
        "train_timestamps": timestamps[target_indices[train_idx]],
        "val_timestamps": timestamps[target_indices[val_idx]],
        "feature_min": feature_min,
        "feature_max": feature_max,
        "pm25_min": pm25_min,
        "pm25_max": pm25_max,
        "raw_targets": raw_targets,
        "clipped_targets": clipped_targets,
    }


def prepare_simulation_shard(
    raw: pd.DataFrame,
    config: dict[str, Any],
    *,
    n_workers: int,
    shard_index: int,
    window_hours: int = 24,
    node_prefix: str = "sim",
    horizon: int = 1,
    val_fraction_of_train: float | None = None,
) -> dict[str, Any]:
    """Prepare only one shard, so a 100-worker run does not build all of them."""
    if "scaler" not in config:
        raise ValueError(
            "config.json has no scaler; run: python -m common.preprocess --build-config"
        )
    val_fraction = float(
        config.get("val_fraction_of_train", 0.1)
        if val_fraction_of_train is None
        else val_fraction_of_train
    )
    if not 0.0 < val_fraction < 1.0:
        raise ValueError("val_fraction_of_train must be between 0 and 1")

    plan = build_shard_plan(config, raw, n_workers=n_workers)
    item = next(
        (entry for entry in plan if entry.shard_index == shard_index), None
    )
    if item is None:
        raise ValueError(
            f"shard_index {shard_index} is outside 0..{len(plan) - 1}"
        )
    train_fraction = float(config.get("train_fraction", 0.8))
    frame = _year_train_frame(raw, item.year, train_fraction)
    segment = frame.iloc[item.start_row : item.end_row]
    prepared = _prepare_shard(
        segment,
        config=config,
        window_hours=window_hours,
        horizon=horizon,
        train_fraction_of_windows=1.0 - val_fraction,
    )
    worker_id = f"{node_prefix}-{item.shard_index + 1}"
    prepared.update(
        {
            "node_id": worker_id,
            "year": int(item.year),
            "shard_index": int(item.shard_index),
            "shard_count": int(item.shard_count),
            "train_rows": int(item.start_row),
            "shard_start_row": int(item.start_row),
            "shard_end_row": int(item.end_row),
            "source_rows": int(item.end_row - item.start_row),
        }
    )
    return {
        "worker_id": worker_id,
        "node_id": worker_id,
        "role": "training",
        "dataset": "simulation",
        "year": int(item.year),
        "shard_index": int(item.shard_index),
        "shard_count": int(item.shard_count),
        "n_samples": len(prepared["X_train"]),
        "n_val": len(prepared["X_val"]),
        "prepared": prepared,
    }


def prepare_simulation_shards(
    raw: pd.DataFrame,
    config: dict[str, Any],
    *,
    n_workers: int,
    window_hours: int = 24,
    node_prefix: str = "sim",
    horizon: int = 1,
    val_fraction_of_train: float | None = None,
) -> list[dict[str, Any]]:
    """Return one fully prepared, disjoint dataset per simulated worker."""
    return [
        prepare_simulation_shard(
            raw,
            config,
            n_workers=n_workers,
            shard_index=index,
            window_hours=window_hours,
            node_prefix=node_prefix,
            horizon=horizon,
            val_fraction_of_train=val_fraction_of_train,
        )
        for index in range(n_workers)
    ]


__all__ = [
    "ShardPlan",
    "build_shard_plan",
    "prepare_simulation_shard",
    "prepare_simulation_shards",
    "training_years",
]
