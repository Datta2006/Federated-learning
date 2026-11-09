"""Performance metrics assembled from the project's existing experiment files.

No metric is recomputed or invented here.  The dashboard reads:

* ``results.csv`` (aggregate rows, mean/std across seeds)
* ``results_by_seed.csv`` (seed-wise rows)
* ``stage4_summary.json`` (aggregate, per-seed registry outcomes, node5)
* the active registry's ``rounds.csv`` (validation loss and communication bytes)
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

NUMERIC_KEYS = {
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
    "seed",
    "rmse_raw",
    "mae_raw",
    "r2_raw",
    "rmse_clipped",
    "mae_clipped",
    "r2_clipped",
    "epochs",
    "train_seconds",
}

METHOD_LABELS = {
    "centralized": "Centralized (paper pipeline)",
    "centralized_improved_w12": "Centralized improved 12 h",
    "centralized_improved_w12_h6": "Centralized improved 12 h / 6 h",
    "centralized_improved_w24": "Centralized improved 24 h (5 nodes)",
    "centralized_improved_w24_4nodes": "Centralized improved 24 h (4 nodes)",
    "federated_improved_w24": "FedAvg improved 24 h",
    "local_only": "Local-only (paper pipeline)",
    "local_only_improved_w12": "Local-only improved 12 h",
    "local_only_improved_w24": "Local-only improved 24 h (5 nodes)",
    "local_only_improved_w24_4nodes": "Local-only improved 24 h (4 nodes)",
    "persistence": "Persistence",
    "persistence_w12": "Persistence 12 h",
    "persistence_w12_h6": "Persistence 12 h / 6 h",
    "persistence_w24": "Persistence 24 h",
    "persistence_w24_4nodes": "Persistence 24 h (4 nodes)",
    "pm25_only": "PM2.5-only ablation",
}

COMPARISON_METHODS = [
    {
        "method": "persistence_w24_4nodes",
        "fallbacks": ["persistence_w24", "persistence"],
        "short": "Persistence",
        "color": "#94a3b8",
        "description": "Next hour equals the current observed PM2.5 value.",
    },
    {
        "method": "local_only_improved_w24_4nodes",
        "fallbacks": ["local_only_improved_w24", "local_only"],
        "short": "Local-only",
        "color": "#f59e0b",
        "description": "Each node trains alone; no weights leave the node.",
    },
    {
        "method": "centralized_improved_w24_4nodes",
        "fallbacks": ["centralized_improved_w24", "centralized"],
        "short": "Centralized",
        "color": "#60a5fa",
        "description": "One pooled-data model over the same four node-years.",
    },
    {
        "method": "federated_improved_w24",
        "fallbacks": [],
        "short": "FedAvg",
        "color": "#34d399",
        "description": "Four training nodes, chunked updates, weighted FedAvg.",
    },
]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in NUMERIC_KEYS:
            cleaned[key] = _number(value)
        else:
            cleaned[key] = value
    return cleaned


def parse_results_csv(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    return [_clean_row(row) for row in csv.DictReader(io.StringIO(text))]


def parse_seed_csv(text: str) -> list[dict[str, Any]]:
    rows = parse_results_csv(text)
    rows.sort(key=lambda row: (str(row.get("method")), row.get("seed") or 0))
    return rows


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def _pick_method(
    rows: list[dict[str, Any]], entry: dict[str, Any]
) -> dict[str, Any] | None:
    by_name = {str(row.get("method")): row for row in rows}
    for name in [entry["method"], *entry["fallbacks"]]:
        if name in by_name:
            row = dict(by_name[name])
            row["label"] = METHOD_LABELS.get(name, name)
            row["short"] = entry["short"]
            row["color"] = entry["color"]
            row["description"] = entry["description"]
            row["requested_method"] = entry["method"]
            return row
    return None


def build_comparison(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    comparison = []
    for entry in COMPARISON_METHODS:
        picked = _pick_method(rows, entry)
        if picked is not None:
            comparison.append(picked)
    return comparison


def _read_summary(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _round_loss_history(rounds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history = []
    for row in rounds:
        loss = row.get("weighted_val_loss")
        history.append(
            {
                "round": row.get("round"),
                "weighted_val_loss": loss,
                "evaluated_version": row.get("evaluated_version"),
                "model_version": row.get("model_version"),
                "available": loss is not None,
            }
        )
    return history


def build_metrics(
    *,
    results_path: Path,
    seed_path: Path,
    summary_path: Path,
    rounds: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = parse_results_csv(read_text(results_path))
    seed_rows = parse_seed_csv(read_text(seed_path))
    summary = _read_summary(summary_path)

    comparison = build_comparison(rows)
    comparison_names = {row.get("method") for row in comparison}
    all_methods = []
    for row in rows:
        name = str(row.get("method"))
        all_methods.append(
            {
                **row,
                "label": METHOD_LABELS.get(name, name),
                "in_comparison": name in comparison_names,
            }
        )

    seed_comparison = [
        row for row in seed_rows if row.get("method") in comparison_names
    ]
    losses = _round_loss_history(rounds)
    loss_values = [
        item["weighted_val_loss"]
        for item in losses
        if item["weighted_val_loss"] is not None
    ]

    return {
        "available": bool(rows),
        "sources": {
            "results_csv": str(results_path.name),
            "results_by_seed_csv": str(seed_path.name),
            "stage4_summary": str(summary_path.name) if summary else None,
        },
        "headline": (summary or {}).get("aggregate", {}).get("headline")
        or "raw_unclipped",
        "comparison": comparison,
        "all_methods": all_methods,
        "seed_results": seed_comparison,
        "federated_seed_results": (summary or {}).get("seed_results", []),
        "unseen_node5": (summary or {}).get("unseen_node5"),
        "bytes": (summary or {}).get("bytes"),
        "aggregate": (summary or {}).get("aggregate"),
        "loss_history": losses,
        "loss_summary": {
            "available": bool(loss_values),
            "latest": loss_values[-1] if loss_values else None,
            "best": min(loss_values) if loss_values else None,
            "note": (
                "Weighted validation loss is read from rounds.csv. The existing "
                "node pipeline does not log per-epoch training loss, so the "
                "dashboard does not invent one."
            ),
        },
        "notes": (
            "All values come from existing experiment outputs. Raw targets are "
            "the project's headline; clipped targets are secondary."
        ),
    }
