"""Shared preparation, metric, aggregation, and reporting helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from common.config import PROJECT_ROOT, load_config, resolve_path
from common.preprocess import inverse_minmax, load_raw, prepare_node_windows

METRICS = ("rmse", "mae", "r2")
TARGETS = ("raw", "clipped")
HEADLINE = "raw_unclipped"

RESULT_COLUMNS = [
    "method",
    "n_seeds",
    "seeds",
    "n_train",
    "n_test",
    "rmse_raw_mean",
    "rmse_raw_std",
    "mae_raw_mean",
    "mae_raw_std",
    "r2_raw_mean",
    "r2_raw_std",
    "rmse_clipped_mean",
    "rmse_clipped_std",
    "mae_clipped_mean",
    "mae_clipped_std",
    "r2_clipped_mean",
    "r2_clipped_std",
    "parameters",
    "epochs_mean",
    "train_seconds_mean",
    "headline",
    "created_utc",
    "notes",
]

SEED_COLUMNS = [
    "method",
    "seed",
    "n_train",
    "n_test",
    "rmse_raw",
    "mae_raw",
    "r2_raw",
    "rmse_clipped",
    "mae_clipped",
    "r2_clipped",
    "parameters",
    "epochs",
    "train_seconds",
    "created_utc",
]

PER_NODE_COLUMNS = [
    "node_id",
    "year",
    "n_train",
    "n_test",
    "rmse_raw_mean",
    "rmse_raw_std",
    "mae_raw_mean",
    "mae_raw_std",
    "r2_raw_mean",
    "r2_raw_std",
    "rmse_clipped_mean",
    "rmse_clipped_std",
    "mae_clipped_mean",
    "mae_clipped_std",
    "r2_clipped_mean",
    "r2_clipped_std",
    "epochs_mean",
    "train_seconds_mean",
]


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def load_prepared(
    config_path: str | Path | None = None,
) -> tuple[dict[str, Any], pd.DataFrame, dict[str, dict[str, Any]]]:
    """Load config, raw data, and one prepared window set per node."""
    config = load_config(config_path)
    scaler = config.get("scaler")
    if not scaler:
        raise ValueError(
            "config.json has no scaler; run: python -m common.preprocess --build-config"
        )

    data_path = resolve_path(config["dataset_path"])
    raw = load_raw(data_path)
    prepared: dict[str, dict[str, Any]] = {}
    for node_id, year in config["nodes"].items():
        prepared[node_id] = prepare_node_windows(
            raw,
            node_id=node_id,
            year=int(year),
            scaler=scaler,
            features=list(config["features"]),
            window_hours=int(config["window_hours"]),
            train_fraction=float(config["train_fraction"]),
            val_fraction_of_train=float(config["val_fraction_of_train"]),
        )
    return config, raw, prepared


def evaluate_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    """Compute RMSE, MAE, and R2 after a length check."""
    truth = np.asarray(y_true, dtype=float).reshape(-1)
    prediction = np.asarray(y_pred, dtype=float).reshape(-1)
    if truth.shape != prediction.shape:
        raise ValueError("y_true and y_pred must have the same length")
    if truth.size < 2:
        raise ValueError("at least two points are required for R2")
    return {
        "rmse": float(np.sqrt(mean_squared_error(truth, prediction))),
        "mae": float(mean_absolute_error(truth, prediction)),
        "r2": float(r2_score(truth, prediction)),
    }


def evaluate_targets(
    prediction: np.ndarray,
    y_test_raw: np.ndarray,
    y_test_clipped: np.ndarray,
) -> dict[str, float]:
    """Score one prediction vector against raw and clipped test targets."""
    raw = evaluate_metrics(y_test_raw, prediction)
    clipped = evaluate_metrics(y_test_clipped, prediction)
    return {
        **{f"{metric}_raw": value for metric, value in raw.items()},
        **{f"{metric}_clipped": value for metric, value in clipped.items()},
    }


def inverse_pm25(scaled_values: np.ndarray, prepared: dict[str, Any]) -> np.ndarray:
    """Map scaled PM2.5 back to physical units and clip negatives to zero."""
    values = np.asarray(scaled_values, dtype=np.float32).reshape(-1, 1)
    restored = inverse_minmax(
        values,
        np.asarray([prepared["pm25_min"]], dtype=np.float32),
        np.asarray([prepared["pm25_max"]], dtype=np.float32),
    ).reshape(-1)
    return np.maximum(restored, 0.0)


def make_seed_result(
    method: str,
    seed: int,
    *,
    n_train: int,
    n_test: int,
    metrics: dict[str, float],
    parameters: int,
    epochs: float,
    train_seconds: float,
) -> dict[str, Any]:
    """Build one long-format result row for results_by_seed.csv."""
    return {
        "method": method,
        "seed": int(seed),
        "n_train": int(n_train),
        "n_test": int(n_test),
        **metrics,
        "parameters": int(parameters),
        "epochs": float(epochs),
        "train_seconds": round(float(train_seconds), 3),
        "created_utc": utc_now_iso(),
    }


def _mean_std(values: Iterable[float]) -> tuple[float, float]:
    array = np.asarray(list(values), dtype=float)
    if array.size == 0:
        raise ValueError("cannot aggregate an empty result set")
    std = float(np.std(array, ddof=1)) if array.size > 1 else 0.0
    if std < 1e-12:
        std = 0.0
    return float(np.mean(array)), std


def aggregate_seed_results(
    method: str,
    seed_rows: list[dict[str, Any]],
    notes: str,
) -> dict[str, Any]:
    """Collapse per-seed rows into mean/std columns for results.csv."""
    if not seed_rows:
        raise ValueError(f"no seed results for {method}")
    first = seed_rows[0]
    result: dict[str, Any] = {
        "method": method,
        "n_seeds": len(seed_rows),
        "seeds": ",".join(str(row["seed"]) for row in seed_rows),
        "n_train": int(first["n_train"]),
        "n_test": int(first["n_test"]),
        "headline": HEADLINE,
        "created_utc": utc_now_iso(),
        "notes": notes,
    }
    for target in TARGETS:
        for metric in METRICS:
            mean, std = _mean_std(
                row[f"{metric}_{target}"] for row in seed_rows
            )
            result[f"{metric}_{target}_mean"] = mean
            result[f"{metric}_{target}_std"] = std

    result["parameters"] = int(first["parameters"])
    result["epochs_mean"], _ = _mean_std(row["epochs"] for row in seed_rows)
    result["train_seconds_mean"], _ = _mean_std(
        row["train_seconds"] for row in seed_rows
    )
    return result


def aggregate_per_node_results(
    node_seed_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse per-node seed rows into mean/std rows for the CSV report."""
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in node_seed_rows:
        grouped.setdefault((row["node_id"], int(row["year"])), []).append(row)

    output: list[dict[str, Any]] = []
    for (node_id, year), rows in sorted(grouped.items()):
        first = rows[0]
        aggregate: dict[str, Any] = {
            "node_id": node_id,
            "year": year,
            "n_train": int(first["n_train"]),
            "n_test": int(first["n_test"]),
        }
        for target in TARGETS:
            for metric in METRICS:
                mean, std = _mean_std(
                    row[f"{metric}_{target}"] for row in rows
                )
                aggregate[f"{metric}_{target}_mean"] = mean
                aggregate[f"{metric}_{target}_std"] = std
        aggregate["epochs_mean"], _ = _mean_std(row["epochs"] for row in rows)
        aggregate["train_seconds_mean"], _ = _mean_std(
            row["train_seconds"] for row in rows
        )
        output.append(aggregate)
    return output


def save_aggregate_results(
    config: dict[str, Any],
    aggregate_rows: list[dict[str, Any]],
    seed_rows: list[dict[str, Any]],
) -> tuple[Path, Path]:
    """Upsert aggregate and per-seed results into CSV files."""
    results_path = resolve_path(config["paths"]["results_csv"])
    seed_path = results_path.with_name("results_by_seed.csv")
    results_path.parent.mkdir(parents=True, exist_ok=True)

    if results_path.exists():
        existing = pd.read_csv(results_path)
        methods = {row["method"] for row in aggregate_rows}
        existing = existing[~existing["method"].isin(methods)]
        combined = pd.concat(
            [existing, pd.DataFrame(aggregate_rows, columns=RESULT_COLUMNS)],
            ignore_index=True,
        )
    else:
        combined = pd.DataFrame(aggregate_rows, columns=RESULT_COLUMNS)
    combined = combined.reindex(columns=RESULT_COLUMNS)
    combined = combined.sort_values("method").reset_index(drop=True)
    combined.to_csv(results_path, index=False)

    new_seed_frame = pd.DataFrame(seed_rows, columns=SEED_COLUMNS)
    if seed_path.exists():
        old_seed_frame = pd.read_csv(seed_path)
        # Replace every seed row for the methods being rewritten so a smoke run
        # cannot leave stale 43/44 rows beside a one-seed aggregate.
        methods = {row["method"] for row in aggregate_rows}
        old_seed_frame = old_seed_frame[~old_seed_frame["method"].isin(methods)]
        seed_frame = pd.concat(
            [old_seed_frame, new_seed_frame], ignore_index=True
        )
    else:
        seed_frame = new_seed_frame
    seed_frame = seed_frame.sort_values(["method", "seed"]).reset_index(drop=True)
    seed_frame.to_csv(seed_path, index=False)
    return results_path, seed_path


def save_per_node_results(node_rows: list[dict[str, Any]]) -> Path:
    """Write mean/std local-only metrics per node."""
    path = PROJECT_ROOT / "baselines" / "local_only_per_node.csv"
    frame = pd.DataFrame(node_rows, columns=PER_NODE_COLUMNS)
    frame = frame.sort_values("node_id").reset_index(drop=True)
    frame.to_csv(path, index=False)
    return path


def plot_results(config: dict[str, Any]) -> Path:
    """Plot raw-headline and clipped metrics with seed error bars."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    results_path = resolve_path(config["paths"]["results_csv"])
    plot_path = resolve_path(config["paths"]["results_plot"])
    if not results_path.exists():
        raise FileNotFoundError(f"no results to plot: {results_path}")

    frame = pd.read_csv(results_path)
    order = [
        "persistence",
        "persistence_w12",
        "persistence_w24",
        "persistence_w12_h6",
        "persistence_w24_4nodes",
        "centralized",
        "centralized_improved_w12",
        "centralized_improved_w24",
        "centralized_improved_w12_h6",
        "centralized_improved_w24_4nodes",
        "local_only",
        "local_only_improved_w12",
        "local_only_improved_w24",
        "local_only_improved_w24_4nodes",
        "federated_improved_w24",
        "pm25_only",
    ]
    frame["_order"] = frame["method"].map(
        {name: index for index, name in enumerate(order)}
    ).fillna(len(order))
    frame = frame.sort_values(["_order", "method"]).reset_index(drop=True)
    methods = frame["method"].tolist()
    x = np.arange(len(methods))
    width = 0.36

    panels = [
        ("rmse", "RMSE", "PM2.5 (ug/m3)", False),
        ("mae", "MAE", "PM2.5 (ug/m3)", False),
        ("r2", "R2", "R2", True),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    for axis, (metric, title, ylabel, is_r2) in zip(axes, panels):
        raw_mean = frame[f"{metric}_raw_mean"].to_numpy()
        raw_std = frame[f"{metric}_raw_std"].to_numpy()
        clipped_mean = frame[f"{metric}_clipped_mean"].to_numpy()
        clipped_std = frame[f"{metric}_clipped_std"].to_numpy()
        axis.bar(
            x - width / 2,
            raw_mean,
            width,
            yerr=raw_std,
            capsize=4,
            label="raw unclipped (headline)",
            color="#1f77b4",
        )
        axis.bar(
            x + width / 2,
            clipped_mean,
            width,
            yerr=clipped_std,
            capsize=4,
            label="clipped at p99.5",
            color="#9ecae1",
            hatch="//",
        )
        axis.set_xticks(x)
        axis.set_xticklabels(methods, rotation=15)
        axis.set_ylabel(ylabel)
        axis.set_title(title)
        axis.grid(axis="y", alpha=0.3)
        if is_r2:
            low = min(
                float(np.min(raw_mean - raw_std)),
                float(np.min(clipped_mean - clipped_std)),
                0.0,
            )
            axis.set_ylim(max(-0.2, low - 0.05), 1.0)

    axes[0].legend(loc="upper right", fontsize=8)
    fig.suptitle(
        "Beijing PM2.5 baselines: next-hour and 6-hour horizon, "
        "mean over 3 seeds, error bars = std"
    )
    fig.tight_layout()
    plot_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)
    return plot_path
