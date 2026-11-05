"""Offline final scoring for a registered federated model.

The coordinator never scores the test split.  It only tracks each node's
validation loss during a round.  This separate script loads a registered model
(``best.json`` by default, or an explicit ``--version``), rebuilds the improved
24 h pipeline for every node, predicts each node's last-20% test slice, and
reports per-node and pooled metrics.

The raw, unclipped targets are the headline; clipped metrics are secondary.
Nodes listed as inference-only in the config (node5) are reported separately as
unseen data and never contribute to the pooled training-node score.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from baselines.common import evaluate_targets, utc_now_iso
from common.config import (
    inference_only_node_ids,
    load_config,
    resolve_path,
    training_node_ids,
)

LOGGER = logging.getLogger(__name__)

METRIC_KEYS = (
    "rmse_raw",
    "mae_raw",
    "r2_raw",
    "rmse_clipped",
    "mae_clipped",
    "r2_clipped",
)


class OfflineEvalError(RuntimeError):
    """Raised when the registry or prepared data cannot be scored."""


def resolve_registry(
    model_dir: str | Path,
    version: str | None = None,
    *,
    prefer_best: bool = False,
) -> tuple[dict[str, Any], Path]:
    """Return the registry record and weight path for a version or the latest model.

    The default is ``latest.json``: the final federated round produces the model
    that has seen every round of aggregation, but that version has not been
    evaluated by any node yet.  Pass *prefer_best* to load ``best.json``, the
    evaluated version with the lowest weighted validation loss.
    """
    directory = Path(model_dir).expanduser().resolve()
    if version is not None:
        record_path = directory / f"global_{version}.json"
        if not record_path.exists():
            raise OfflineEvalError(f"registry record not found: {record_path}")
    elif prefer_best:
        record_path = directory / "best.json"
        if not record_path.exists():
            raise OfflineEvalError(f"no best.json under {directory}")
    else:
        record_path = directory / "latest.json"
        if not record_path.exists():
            raise OfflineEvalError(f"no latest.json under {directory}")
    with record_path.open("r", encoding="utf-8") as handle:
        record = json.load(handle)
    resolved_version = str(record.get("model_version", ""))
    if not resolved_version:
        raise OfflineEvalError(f"{record_path} has no model_version")
    if version is not None and resolved_version != version:
        raise OfflineEvalError(
            f"{record_path} describes {resolved_version}, not {version}"
        )
    weights_path = directory / f"global_{resolved_version}.npy"
    if not weights_path.exists():
        raise OfflineEvalError(f"weights not found: {weights_path}")
    return record, weights_path


def pooled_metrics(
    predictions: dict[str, np.ndarray],
    prepared: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Concatenate node test slices and score them once as a pooled set."""
    if not predictions:
        raise ValueError("at least one node prediction is required")
    missing = set(predictions).difference(prepared)
    if missing:
        raise ValueError(f"missing prepared data for {sorted(missing)}")
    ordered = sorted(predictions)
    prediction = np.concatenate(
        [np.asarray(predictions[node], dtype=float).reshape(-1) for node in ordered]
    )
    raw = np.concatenate(
        [
            np.asarray(prepared[node]["y_test_raw"], dtype=float).reshape(-1)
            for node in ordered
        ]
    )
    clipped = np.concatenate(
        [
            np.asarray(prepared[node]["y_test_clipped"], dtype=float).reshape(-1)
            for node in ordered
        ]
    )
    return {
        "nodes": ordered,
        "n_test": int(prediction.size),
        "metrics": evaluate_targets(prediction, raw, clipped),
    }


def score_node(
    prepared: dict[str, Any],
    model: Any,
    *,
    batch_size: int = 64,
) -> tuple[dict[str, Any], np.ndarray]:
    """Predict one node's test slice and return its result plus prediction."""
    from common.improved import reconstruct_pm25

    scaled = model.predict(
        prepared["X_test"], batch_size=batch_size, verbose=0
    ).reshape(-1)
    prediction = reconstruct_pm25(scaled, prepared)
    metrics = evaluate_targets(
        prediction, prepared["y_test_raw"], prepared["y_test_clipped"]
    )
    result = {
        "node_id": prepared["node_id"],
        "year": int(prepared["year"]),
        "n_test": int(prediction.size),
        "metrics": metrics,
        "prediction_min": float(np.min(prediction)),
        "prediction_max": float(np.max(prediction)),
        "prediction_mean": float(np.mean(prediction)),
    }
    return result, prediction


def prepare_nodes(
    config: dict[str, Any],
    node_ids: list[str],
    raw: Any,
    model_config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Prepare the exact window/target pipeline described by *model_config*."""
    from common.improved import prepare_improved_nodes

    return prepare_improved_nodes(
        config,
        raw,
        window_hours=int(model_config.get("window_hours", 24)),
        horizon=int(model_config.get("horizon", 1)),
        delta=bool(model_config.get("delta", True)),
        cyclic_hour=bool(model_config.get("cyclic_hour", True)),
        node_ids=node_ids,
    )


def evaluate_registry(
    config_path: str | Path | None = None,
    *,
    model_dir: str | Path | None = None,
    version: str | None = None,
    prefer_best: bool = False,
    batch_size: int = 64,
    verbose: int = 0,
) -> dict[str, Any]:
    """Score the registered model on every training node and the unseen nodes."""
    from common.model import build_model_from_config, unflatten_weights
    from common.preprocess import load_raw

    config = load_config(config_path)
    configured_dir = config.get("paths", {}).get("model_dir", "server/model_registry")
    directory = (
        Path(model_dir).expanduser().resolve()
        if model_dir is not None
        else resolve_path(configured_dir)
    )
    record, weights_path = resolve_registry(
        directory, version=version, prefer_best=prefer_best
    )
    model_config = dict(record.get("model") or {})
    if not model_config:
        raise OfflineEvalError(
            f"{weights_path} has no model architecture metadata; "
            "dummy registries cannot be scored offline"
        )
    weights = np.load(weights_path, allow_pickle=False)

    training = sorted(training_node_ids(config))
    unseen = sorted(inference_only_node_ids(config))
    raw = load_raw(resolve_path(config["dataset_path"]))
    prepared = prepare_nodes(config, training + unseen, raw, model_config)

    # Build once so a bad weight count or architecture fails before prediction.
    model = build_model_from_config(model_config)
    unflatten_weights(model, weights)

    node_results: dict[str, Any] = {}
    predictions: dict[str, np.ndarray] = {}
    for node_id in training:
        result, prediction = score_node(
            prepared[node_id], model, batch_size=batch_size
        )
        node_results[node_id] = result
        predictions[node_id] = prediction
        if verbose:
            print(
                f"{node_id}: n_test={result['n_test']} "
                f"rmse_raw={result['metrics']['rmse_raw']:.4f} "
                f"mae_raw={result['metrics']['mae_raw']:.4f} "
                f"r2_raw={result['metrics']['r2_raw']:.4f}",
                flush=True,
            )

    unseen_results: dict[str, Any] = {}
    for node_id in unseen:
        unseen_results[node_id], _ = score_node(
            prepared[node_id], model, batch_size=batch_size
        )

    return {
        "created_utc": utc_now_iso(),
        "model_version": record["model_version"],
        "round": record.get("round"),
        "evaluated_round": record.get("evaluated_round"),
        "weighted_val_loss": record.get("weighted_val_loss"),
        "model_path": str(weights_path),
        "parameters": int(weights.size),
        "training_nodes": node_results,
        "pooled_training": pooled_metrics(predictions, prepared),
        "unseen_nodes": unseen_results,
    }


def _print_table(result: dict[str, Any]) -> None:
    print(
        "node       n_test  RMSE_raw  MAE_raw  R2_raw   "
        "RMSE_clip  MAE_clip  R2_clip",
        flush=True,
    )
    for label, entry in [
        ("pooled", result["pooled_training"]),
        *[(node, value) for node, value in result["training_nodes"].items()],
        *[
            (f"{node} (unseen)", value)
            for node, value in result["unseen_nodes"].items()
        ],
    ]:
        metrics = entry["metrics"]
        print(
            f"{label:<10} {entry['n_test']:>7}  "
            f"{metrics['rmse_raw']:>8.4f}  {metrics['mae_raw']:>7.4f}  "
            f"{metrics['r2_raw']:>7.4f}  {metrics['rmse_clipped']:>9.4f}  "
            f"{metrics['mae_clipped']:>8.4f}  {metrics['r2_clipped']:>7.4f}",
            flush=True,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Score a registered Stage 4 model on node test slices"
    )
    parser.add_argument("--config", default=None)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--version", default=None)
    parser.add_argument(
        "--best",
        action="store_true",
        help="score best.json (lowest validation loss) instead of latest.json",
    )
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--output", default=None)
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def _main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.verbose == 0 else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = evaluate_registry(
        args.config,
        model_dir=args.model_dir,
        version=args.version,
        prefer_best=args.best,
        batch_size=args.batch_size,
        verbose=args.verbose,
    )
    _print_table(result)
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print(f"wrote {output}", flush=True)
    print(
        f"headline raw unclipped: RMSE={result['pooled_training']['metrics']['rmse_raw']:.6f} "
        f"MAE={result['pooled_training']['metrics']['mae_raw']:.6f} "
        f"R2={result['pooled_training']['metrics']['r2_raw']:.6f}",
        flush=True,
    )


if __name__ == "__main__":
    _main()
