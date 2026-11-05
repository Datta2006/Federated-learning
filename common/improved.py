"""Improved window builder: delta targets, longer horizons, cyclic hour.

The paper-faithful pipeline in :mod:`common.preprocess` is deliberately left
untouched.  This module is a single deep seam for the improved variant:

    prepare_improved_node(...)  -> fully split train/val/test arrays
    reconstruct_pm25(...)       -> physical PM2.5 from test predictions

A target can be either the scaled future value (``delta=False``) or the scaled
change from the last observed hour (``delta=True``).  Windows may look
``horizon`` hours ahead, and the hour-of-day sin/cos pair can be appended as
extra inputs so the model can learn diurnal structure.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from common.preprocess import (
    clean_pm25_series,
    fill_pm25_series,
    inverse_minmax,
    minmax_scale,
)


def improved_model_config(
    config: dict[str, Any], *, window_hours: int = 24, seed: int = 42
) -> dict[str, Any]:
    """Return the shared improved-24h architecture metadata.

    Nodes, the server, and registered models all use this one description, so a
    received weight vector can always be rebuilt into the same Keras graph.
    """
    model_cfg = config.get("model", {})
    features = list(config.get("features", ["pm25", "temp", "rh"]))
    return {
        "architecture": "cnn_rnn_improved",
        "window_hours": int(window_hours),
        "n_features": len(features) + 2,
        "conv_filters": int(model_cfg.get("conv_filters", 64)),
        "kernel_size": int(model_cfg.get("kernel_size", 2)),
        "pool_size": 1,
        "rnn_units": int(model_cfg.get("rnn_units", 64)),
        "dropout": float(model_cfg.get("dropout", 0.2)),
        "learning_rate": float(model_cfg.get("learning_rate", 0.001)),
        "seed": int(seed),
        "horizon": 1,
        "delta": True,
        "cyclic_hour": True,
    }


def prepare_improved_node(
    raw: pd.DataFrame,
    node_id: str,
    year: int,
    scaler: dict[str, Any],
    features: list[str],
    *,
    window_hours: int,
    horizon: int = 1,
    delta: bool = True,
    cyclic_hour: bool = True,
    train_fraction: float,
    val_fraction_of_train: float,
) -> dict[str, Any]:
    """Clean, scale, window, and split one node for the improved variant."""
    if window_hours < 1:
        raise ValueError("window_hours must be at least 1")
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0.0 <= val_fraction_of_train < 1.0:
        raise ValueError("val_fraction_of_train must be in [0, 1)")
    if "pm25" not in features:
        raise ValueError("features must include pm25")

    node_frame = (
        raw.loc[raw["year"] == year]
        .sort_values("timestamp")
        .copy()
        .reset_index(drop=True)
    )
    if node_frame.empty:
        raise ValueError(f"{node_id}: no rows for year {year}")

    split_row = int(len(node_frame) * train_fraction)
    if split_row < 1 or split_row >= len(node_frame):
        raise ValueError(f"{node_id}: invalid train/test split at row {split_row}")

    train_frame = node_frame.iloc[:split_row].copy()
    test_frame = node_frame.iloc[split_row:].copy()
    clip_value = float(scaler["pm25_clip"])
    train_frame["pm25_raw"] = fill_pm25_series(train_frame["pm2.5"])
    test_frame["pm25_raw"] = fill_pm25_series(test_frame["pm2.5"])
    train_frame["pm25"] = clean_pm25_series(train_frame["pm2.5"], clip_value)
    test_frame["pm25"] = clean_pm25_series(test_frame["pm2.5"], clip_value)
    node_frame = pd.concat([train_frame, test_frame]).sort_index()

    feature_min = np.asarray(scaler["feature_min"], dtype=np.float32)
    feature_max = np.asarray(scaler["feature_max"], dtype=np.float32)
    scaled = minmax_scale(
        node_frame[features].to_numpy(dtype=np.float32), feature_min, feature_max
    )

    pm25_index = features.index("pm25")
    pm25_scaled = scaled[:, pm25_index].astype(np.float32, copy=True)
    pm25_min = float(feature_min[pm25_index])
    pm25_max = float(feature_max[pm25_index])

    if cyclic_hour:
        hours = node_frame["timestamp"].dt.hour.to_numpy(dtype=np.float32)
        angle = 2.0 * np.pi * hours / 24.0
        scaled = np.hstack(
            [scaled, np.sin(angle)[:, None], np.cos(angle)[:, None]]
        ).astype(np.float32, copy=False)

    target_scaled = minmax_scale(
        node_frame["pm25"].to_numpy(dtype=np.float32).reshape(-1, 1),
        np.asarray([pm25_min], dtype=np.float32),
        np.asarray([pm25_max], dtype=np.float32),
    ).reshape(-1)
    raw_targets = node_frame["pm25_raw"].to_numpy(dtype=np.float32)
    clipped_targets = node_frame["pm25"].to_numpy(dtype=np.float32)
    timestamps = node_frame["timestamp"].to_numpy()

    sample_count = len(scaled) - window_hours - horizon + 1
    if sample_count < 2:
        raise ValueError(
            f"{node_id}: not enough rows for window={window_hours}, horizon={horizon}"
        )
    starts = np.arange(sample_count, dtype=int)
    target_indices = starts + window_hours - 1 + horizon
    current_indices = starts + window_hours - 1
    X = np.stack(
        [scaled[start : start + window_hours] for start in starts]
    ).astype(np.float32)

    if delta:
        y = (
            target_scaled[target_indices] - pm25_scaled[current_indices]
        ).astype(np.float32)
    else:
        y = target_scaled[target_indices].astype(np.float32)

    train_positions = np.flatnonzero(target_indices < split_row)
    test_positions = np.flatnonzero(target_indices >= split_row)
    if len(train_positions) < 2 or len(test_positions) < 1:
        raise ValueError(f"{node_id}: not enough windows for train/test split")

    val_count = round(len(train_positions) * val_fraction_of_train)
    train_cut = len(train_positions) - val_count
    if train_cut < 1:
        raise ValueError(
            f"{node_id}: not enough training windows after validation split"
        )

    train_idx = train_positions[:train_cut]
    val_idx = train_positions[train_cut:]
    test_idx = test_positions

    return {
        "node_id": node_id,
        "year": int(year),
        "window_hours": int(window_hours),
        "horizon": int(horizon),
        "delta": bool(delta),
        "cyclic_hour": bool(cyclic_hour),
        "n_features": int(scaled.shape[1]),
        "X_train": X[train_idx],
        "y_train": y[train_idx],
        "X_val": X[val_idx],
        "y_val": y[val_idx],
        "X_test": X[test_idx],
        "y_test": y[test_idx],
        "y_test_raw": raw_targets[target_indices[test_idx]],
        "y_test_clipped": clipped_targets[target_indices[test_idx]],
        "current_test_pm25_raw": raw_targets[current_indices[test_idx]],
        "current_test_pm25_clipped": clipped_targets[current_indices[test_idx]],
        "current_test_scaled": pm25_scaled[current_indices[test_idx]],
        "test_timestamps": timestamps[target_indices[test_idx]],
        "train_timestamps": timestamps[target_indices[train_idx]],
        "feature_min": feature_min,
        "feature_max": feature_max,
        "pm25_min": pm25_min,
        "pm25_max": pm25_max,
    }


def prepare_improved_nodes(
    config: dict[str, Any],
    raw: pd.DataFrame,
    *,
    window_hours: int,
    horizon: int = 1,
    delta: bool = True,
    cyclic_hour: bool = True,
    node_ids: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run :func:`prepare_improved_node` for every node in the config.

    Pass *node_ids* to prepare an explicit subset, e.g. node1-node4 for the fair
    federated comparison that excludes the inference-only node5.
    """
    scaler = config.get("scaler")
    if not scaler:
        raise ValueError(
            "config.json has no scaler; run: python -m common.preprocess --build-config"
        )
    selected = list(node_ids) if node_ids is not None else list(config["nodes"])
    unknown = sorted(set(selected).difference(config["nodes"]))
    if unknown:
        raise ValueError(f"unknown node_id(s): {unknown}")
    return {
        node_id: prepare_improved_node(
            raw,
            node_id=node_id,
            year=int(config["nodes"][node_id]),
            scaler=scaler,
            features=list(config["features"]),
            window_hours=window_hours,
            horizon=horizon,
            delta=delta,
            cyclic_hour=cyclic_hour,
            train_fraction=float(config["train_fraction"]),
            val_fraction_of_train=float(config["val_fraction_of_train"]),
        )
        for node_id in selected
    }


def reconstruct_pm25(
    scaled_predictions: np.ndarray, prepared: dict[str, Any]
) -> np.ndarray:
    """Turn test-set model outputs back into physical PM2.5 (>= 0).

    For ``delta=True`` the prediction is a change from the last observed
    scaled hour, so that hour is added back before inverse Min-Max scaling.
    """
    values = np.asarray(scaled_predictions, dtype=np.float32).reshape(-1)
    if prepared["delta"]:
        values = values + np.asarray(
            prepared["current_test_scaled"], dtype=np.float32
        )
    restored = inverse_minmax(
        values.reshape(-1, 1),
        np.asarray([prepared["pm25_min"]], dtype=np.float32),
        np.asarray([prepared["pm25_max"]], dtype=np.float32),
    ).reshape(-1)
    return np.maximum(restored, 0.0)
