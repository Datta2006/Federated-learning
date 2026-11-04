"""Data loading, PM2.5 cleaning, global scaling, and sliding windows.

Public seams used by tests and baselines:
    load_raw, clean_pm25_series, derive_relative_humidity,
    minmax_scale, inverse_minmax, make_windows,
    compute_global_scaler, prepare_node_windows, build_config_file
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.config import load_config, resolve_path, save_config

REQUIRED_COLUMNS = {
    "year",
    "month",
    "day",
    "hour",
    "pm2.5",
    "DEWP",
    "TEMP",
}


def load_raw(path: str | Path) -> pd.DataFrame:
    """Load the Beijing CSV and add timestamp plus relative humidity.

    No rows are dropped and pm2.5 is not filled here; that is deliberately a
    separate step so callers can keep train/test boundaries under control.
    """
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"dataset not found: {csv_path}")

    frame = pd.read_csv(csv_path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(
            f"{csv_path} is missing required columns: {missing}; "
            f"found columns: {list(frame.columns)}"
        )

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(
        frame[["year", "month", "day", "hour"]], errors="raise"
    )
    frame["rh"] = derive_relative_humidity(frame["TEMP"], frame["DEWP"])
    frame["temp"] = frame["TEMP"].astype(float)
    frame = frame.sort_values("timestamp").reset_index(drop=True)

    duplicates = int(frame["timestamp"].duplicated().sum())
    if duplicates:
        raise ValueError(f"{csv_path} has {duplicates} duplicate timestamps")
    if not frame["hour"].between(0, 23).all():
        raise ValueError(f"{csv_path} contains an hour outside 0..23")
    return frame


def derive_relative_humidity(
    temp_c: float | pd.Series | np.ndarray,
    dewpoint_c: float | pd.Series | np.ndarray,
) -> float | np.ndarray:
    """Magnus-formula relative humidity in percent, clipped to 0..100."""
    temperature = np.asarray(temp_c, dtype=float)
    dewpoint = np.asarray(dewpoint_c, dtype=float)
    numerator = np.exp(17.625 * dewpoint / (243.04 + dewpoint))
    denominator = np.exp(17.625 * temperature / (243.04 + temperature))
    humidity = 100.0 * numerator / denominator
    humidity = np.clip(humidity, 0.0, 100.0)
    if humidity.ndim == 0:
        return float(humidity)
    return humidity


def _fill_pm25_series(values: pd.Series) -> pd.Series:
    """Forward-fill first, then interpolate any remaining (leading) gaps."""
    series = values.astype(float).copy().ffill()
    series = series.interpolate(method="linear", limit_direction="both")
    if series.isna().any():
        raise ValueError("pm2.5 has NA values that could not be filled")
    return series


def clean_pm25_series(values: pd.Series, clip_p995: float) -> pd.Series:
    """Forward-fill, linearly interpolate, then clip PM2.5 at a percentile."""
    series = _fill_pm25_series(values)
    return series.clip(lower=0.0, upper=float(clip_p995))


def make_windows(
    features: np.ndarray,
    target: np.ndarray,
    window_hours: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build (samples, window_hours, features) windows and next-hour targets."""
    values = np.asarray(features, dtype=np.float32)
    targets = np.asarray(target, dtype=np.float32).reshape(-1)
    if values.ndim != 2:
        raise ValueError("features must be a 2-D array")
    if len(values) != len(targets):
        raise ValueError("features and target must have the same length")
    if window_hours < 1:
        raise ValueError("window_hours must be at least 1")
    if len(values) <= window_hours:
        raise ValueError(
            f"need more than {window_hours} rows to build one window; got {len(values)}"
        )

    X = np.stack(
        [values[i : i + window_hours] for i in range(len(values) - window_hours)]
    ).astype(np.float32)
    y = targets[window_hours:].astype(np.float32)
    target_indices = np.arange(window_hours, len(values), dtype=int)
    return X, y, target_indices


def minmax_scale(
    values: np.ndarray, feature_min: np.ndarray, feature_max: np.ndarray
) -> np.ndarray:
    """Scale columns to [0, 1] with the supplied shared min/max."""
    array = np.asarray(values, dtype=np.float32)
    mins = np.asarray(feature_min, dtype=np.float32)
    maxs = np.asarray(feature_max, dtype=np.float32)
    denominator = maxs - mins
    if np.any(denominator == 0):
        raise ValueError("feature max must be greater than feature min")
    return ((array - mins) / denominator).astype(np.float32)


def inverse_minmax(
    values: np.ndarray, feature_min: np.ndarray, feature_max: np.ndarray
) -> np.ndarray:
    """Undo min/max scaling."""
    array = np.asarray(values, dtype=np.float32)
    mins = np.asarray(feature_min, dtype=np.float32)
    maxs = np.asarray(feature_max, dtype=np.float32)
    return (array * (maxs - mins) + mins).astype(np.float32)


def compute_global_scaler(
    raw: pd.DataFrame,
    nodes: dict[str, int],
    features: list[str],
    train_fraction: float,
    clip_quantile: float,
) -> dict[str, Any]:
    """Compute one shared scaler from the training portion of every node.

    The percentile and min/max are fitted on the first ``train_fraction`` of
    each node's year, so held-out test data is not used for scaling.
    """
    if not 0.0 < train_fraction < 1.0:
        raise ValueError("train_fraction must be between 0 and 1")

    years = sorted(set(nodes.values()))
    filled_train_parts: list[np.ndarray] = []
    for year in years:
        year_frame = raw.loc[raw["year"] == year].sort_values("timestamp")
        if year_frame.empty:
            raise ValueError(f"no rows found for node year {year}")
        train_rows = max(1, int(len(year_frame) * train_fraction))
        if train_rows >= len(year_frame):
            raise ValueError(f"year {year} is too short for a train/test split")
        filled = _fill_pm25_series(year_frame["pm2.5"].iloc[:train_rows])
        filled_train_parts.append(filled.to_numpy(dtype=float))

    clip_p995 = float(
        np.quantile(np.concatenate(filled_train_parts), clip_quantile)
    )

    pooled_train: list[np.ndarray] = []
    for year in years:
        year_frame = raw.loc[raw["year"] == year].sort_values("timestamp").copy()
        train_rows = max(1, int(len(year_frame) * train_fraction))
        train_frame = year_frame.iloc[:train_rows].copy()
        train_frame["pm25"] = clean_pm25_series(
            train_frame["pm2.5"], clip_p995
        )
        pooled_train.append(train_frame[features].to_numpy(dtype=float))

    pooled = np.vstack(pooled_train)
    feature_min = pooled.min(axis=0)
    feature_max = pooled.max(axis=0)
    if np.any(feature_max <= feature_min):
        raise ValueError("global scaler has a zero-width feature range")

    return {
        "feature_min": [float(value) for value in feature_min],
        "feature_max": [float(value) for value in feature_max],
        "pm25_clip": clip_p995,
        "trained_rows": int(pooled.shape[0]),
        "trained_years": [int(year) for year in years],
    }


def prepare_node_windows(
    raw: pd.DataFrame,
    node_id: str,
    year: int,
    scaler: dict[str, Any],
    features: list[str],
    window_hours: int,
    train_fraction: float,
    val_fraction_of_train: float,
) -> dict[str, Any]:
    """Clean one node, scale with the global scaler, and split its windows."""
    node_frame = (
        raw.loc[raw["year"] == year].sort_values("timestamp").copy().reset_index(drop=True)
    )
    if node_frame.empty:
        raise ValueError(f"{node_id}: no rows for year {year}")

    split_row = int(len(node_frame) * train_fraction)
    if split_row < 1 or split_row >= len(node_frame):
        raise ValueError(f"{node_id}: invalid train/test split at row {split_row}")
    train_frame = node_frame.iloc[:split_row].copy()
    test_frame = node_frame.iloc[split_row:].copy()
    clip_value = float(scaler["pm25_clip"])
    train_frame["pm25_raw"] = _fill_pm25_series(train_frame["pm2.5"])
    test_frame["pm25_raw"] = _fill_pm25_series(test_frame["pm2.5"])
    train_frame["pm25"] = clean_pm25_series(train_frame["pm2.5"], clip_value)
    test_frame["pm25"] = clean_pm25_series(test_frame["pm2.5"], clip_value)
    node_frame = pd.concat([train_frame, test_frame]).sort_index()

    feature_values = node_frame[features].to_numpy(dtype=np.float32)
    feature_min = np.asarray(scaler["feature_min"], dtype=np.float32)
    feature_max = np.asarray(scaler["feature_max"], dtype=np.float32)
    scaled_features = minmax_scale(feature_values, feature_min, feature_max)

    pm25_index = features.index("pm25")
    pm25_min = feature_min[pm25_index : pm25_index + 1]
    pm25_max = feature_max[pm25_index : pm25_index + 1]
    scaled_target = minmax_scale(
        node_frame["pm25"].to_numpy(dtype=np.float32).reshape(-1, 1),
        pm25_min,
        pm25_max,
    ).reshape(-1)

    X, y, target_indices = make_windows(scaled_features, scaled_target, window_hours)
    timestamps = node_frame["timestamp"].iloc[target_indices].to_numpy()
    raw_targets = node_frame["pm25_raw"].to_numpy(dtype=np.float32)
    clipped_targets = node_frame["pm25"].to_numpy(dtype=np.float32)
    current_indices = target_indices - 1

    train_positions = np.flatnonzero(target_indices < split_row)
    test_positions = np.flatnonzero(target_indices >= split_row)
    if len(train_positions) < 2 or len(test_positions) < 1:
        raise ValueError(f"{node_id}: not enough windows for train/test split")

    val_count = round(len(train_positions) * val_fraction_of_train)
    train_cut = len(train_positions) - val_count
    if train_cut < 1:
        raise ValueError(f"{node_id}: not enough training windows after validation split")

    train_idx = train_positions[:train_cut]
    val_idx = train_positions[train_cut:]
    test_idx = test_positions

    return {
        "node_id": node_id,
        "year": int(year),
        "X_train": X[train_idx],
        "y_train": y[train_idx],
        "X_val": X[val_idx],
        "y_val": y[val_idx],
        "X_test": X[test_idx],
        "y_test": y[test_idx],
        "y_test_clipped": clipped_targets[target_indices[test_idx]],
        "y_test_raw": raw_targets[target_indices[test_idx]],
        "current_test_pm25_clipped": clipped_targets[current_indices[test_idx]],
        "current_test_pm25_raw": raw_targets[current_indices[test_idx]],
        "test_timestamps": timestamps[test_idx],
        "feature_min": feature_min,
        "feature_max": feature_max,
        "pm25_min": float(pm25_min[0]),
        "pm25_max": float(pm25_max[0]),
    }


def build_config_file(config_path: str | Path, dataset_path: str | Path) -> dict[str, Any]:
    """Compute the shared scaler and save it back into config.json."""
    config = load_config(config_path)
    raw = load_raw(dataset_path)
    config["scaler"] = compute_global_scaler(
        raw,
        nodes=config["nodes"],
        features=config["features"],
        train_fraction=float(config["train_fraction"]),
        clip_quantile=float(config["clip_quantile"]),
    )
    save_config(config, config_path)
    return config


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the global PM2.5 scaler stored in config.json"
    )
    parser.add_argument(
        "--config",
        default="common/config.json",
        help="path to config.json (default: common/config.json)",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="dataset path; defaults to dataset_path in config",
    )
    parser.add_argument("--build-config", action="store_true")
    args = parser.parse_args()

    config_path = resolve_path(args.config)
    config = load_config(config_path)
    data_path = resolve_path(args.data or config["dataset_path"])
    if not args.build_config:
        parser.error("pass --build-config to write the scaler into config.json")

    updated = build_config_file(config_path, data_path)
    scaler = updated["scaler"]
    print(f"wrote {config_path}")
    print(f"trained rows: {scaler['trained_rows']}")
    print(f"pm25 clip (p99.5): {scaler['pm25_clip']:.6f}")
    for name, low, high in zip(
        updated["features"], scaler["feature_min"], scaler["feature_max"]
    ):
        print(f"{name}: min={low:.6f} max={high:.6f}")


if __name__ == "__main__":
    _main()
