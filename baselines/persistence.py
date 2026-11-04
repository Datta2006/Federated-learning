"""Persistence baseline: next-hour PM2.5 equals the current-hour PM2.5."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from baselines.common import evaluate_metrics, load_prepared, make_seed_result


def run(
    config_path: str | Path | None = None,
    *,
    seed: int | None = None,
) -> dict:
    """Score the previous observed value as the next-hour forecast."""
    config, _raw, prepared = load_prepared(config_path)
    run_seed = int(seed if seed is not None else config["seed"])

    truth_raw = np.concatenate([item["y_test_raw"] for item in prepared.values()])
    truth_clipped = np.concatenate(
        [item["y_test_clipped"] for item in prepared.values()]
    )
    current_raw = np.concatenate(
        [item["current_test_pm25_raw"] for item in prepared.values()]
    )

    # Score one prediction vector against both target versions, matching the
    # other baselines. The raw current value is the persistence prediction.
    raw = evaluate_metrics(truth_raw, current_raw)
    clipped = evaluate_metrics(truth_clipped, current_raw)
    metrics = {
        **{f"{name}_raw": value for name, value in raw.items()},
        **{f"{name}_clipped": value for name, value in clipped.items()},
    }
    result = make_seed_result(
        "persistence",
        run_seed,
        n_train=0,
        n_test=len(truth_raw),
        metrics=metrics,
        parameters=0,
        epochs=0.0,
        train_seconds=0.0,
    )
    print(
        f"persistence seed={run_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f} | "
        f"clipped RMSE={metrics['rmse_clipped']:.4f} "
        f"MAE={metrics['mae_clipped']:.4f} R2={metrics['r2_clipped']:.4f}"
    )
    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the persistence baseline")
    parser.add_argument("--config", default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    run(args.config, seed=args.seed)


if __name__ == "__main__":
    _main()
