"""Run all Stage 1 baselines over several seeds and report mean +/- std."""

from __future__ import annotations

import argparse

import pandas as pd

from baselines.centralized import run as run_centralized
from baselines.common import (
    aggregate_per_node_results,
    aggregate_seed_results,
    load_prepared,
    plot_results,
    save_aggregate_results,
    save_per_node_results,
)
from baselines.local_only import run as run_local_only
from baselines.persistence import run as run_persistence
from baselines.pm25_only import run as run_pm25_only

METHOD_ORDER = ["centralized", "local_only", "pm25_only", "persistence"]


def _parse_seeds(value: str | None, config: dict) -> list[int]:
    if value:
        seeds = [int(part.strip()) for part in value.split(",") if part.strip()]
        if not seeds:
            raise ValueError("--seeds must contain at least one integer")
        return seeds
    configured = config.get("seeds")
    if isinstance(configured, list) and configured:
        return [int(seed) for seed in configured]
    base = int(config["seed"])
    return [base, base + 1, base + 2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run persistence, centralized, local-only, and PM2.5-only baselines"
    )
    parser.add_argument("--config", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seeds", default=None, help="comma-separated seeds")
    parser.add_argument("--verbose", type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--skip-persistence", action="store_true")
    parser.add_argument("--skip-centralized", action="store_true")
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument("--skip-pm25-only", action="store_true")
    args = parser.parse_args()

    config, _raw, _prepared = load_prepared(args.config)
    seeds = _parse_seeds(args.seeds, config)
    print(f"seeds: {seeds}")

    aggregate_rows: list[dict] = []
    all_seed_rows: list[dict] = []
    node_seed_rows: list[dict] = []

    if not args.skip_persistence:
        first = run_persistence(args.config, seed=seeds[0])
        seed_rows = []
        for seed in seeds:
            row = dict(first)
            row["seed"] = seed
            seed_rows.append(row)
        all_seed_rows.extend(seed_rows)
        aggregate_rows.append(
            aggregate_seed_results(
                "persistence",
                seed_rows,
                "Next-hour PM2.5 equals the current hour. Deterministic, so std=0. "
                "Raw = filled but unclipped targets; clipped = p99.5 targets. "
                "Headline = raw_unclipped.",
            )
        )

    if not args.skip_centralized:
        seed_rows = [
            run_centralized(
                args.config, epochs=args.epochs, verbose=args.verbose, seed=seed
            )
            for seed in seeds
        ]
        all_seed_rows.extend(seed_rows)
        aggregate_rows.append(
            aggregate_seed_results(
                "centralized",
                seed_rows,
                "One model on pooled first-80% windows of all node-years, tested on "
                "the last 20%. Mean/std over seeds. Raw = filled but unclipped "
                "targets; clipped = p99.5 targets. Headline = raw_unclipped.",
            )
        )

    if not args.skip_local:
        seed_rows = []
        for seed in seeds:
            result = run_local_only(
                args.config, epochs=args.epochs, verbose=args.verbose, seed=seed
            )
            node_seed_rows.extend(result.pop("per_node"))
            seed_rows.append(result)
        all_seed_rows.extend(seed_rows)
        aggregate_rows.append(
            aggregate_seed_results(
                "local_only",
                seed_rows,
                "Five independent per-node models, no sharing; per-node test "
                "predictions pooled for one score. Mean/std over seeds. Raw = filled "
                "but unclipped targets; clipped = p99.5 targets. Headline = raw_unclipped.",
            )
        )

    if not args.skip_pm25_only:
        seed_rows = [
            run_pm25_only(
                args.config, epochs=args.epochs, verbose=args.verbose, seed=seed
            )
            for seed in seeds
        ]
        all_seed_rows.extend(seed_rows)
        aggregate_rows.append(
            aggregate_seed_results(
                "pm25_only",
                seed_rows,
                "PM2.5-only ablation: same architecture, splits, and training target "
                "with temp/RH removed. Mean/std over seeds. Raw = filled but "
                "unclipped targets; clipped = p99.5 targets. Headline = raw_unclipped.",
            )
        )

    if not aggregate_rows:
        parser.error("all baselines were skipped")

    aggregate_rows.sort(key=lambda row: METHOD_ORDER.index(row["method"]))
    results_path, seed_path = save_aggregate_results(
        config, aggregate_rows, all_seed_rows
    )
    print(f"saved {results_path} and {seed_path}")
    if node_seed_rows:
        node_path = save_per_node_results(aggregate_per_node_results(node_seed_rows))
        print(f"saved {node_path}")

    plot_path = plot_results(config)
    print(f"saved {plot_path}")

    frame = pd.read_csv(results_path).sort_values(
        "method", key=lambda values: values.map(METHOD_ORDER.index)
    )
    print("\nHeadline raw unclipped metrics (mean +/- std over seeds):")
    for row in frame.itertuples(index=False):
        print(
            f"{row.method:12s} "
            f"RMSE={row.rmse_raw_mean:7.3f} +/- {row.rmse_raw_std:6.3f}  "
            f"MAE={row.mae_raw_mean:7.3f} +/- {row.mae_raw_std:6.3f}  "
            f"R2={row.r2_raw_mean:6.4f} +/- {row.r2_raw_std:6.4f}"
        )
    print("\nClipped-target metrics (secondary):")
    for row in frame.itertuples(index=False):
        print(
            f"{row.method:12s} "
            f"RMSE={row.rmse_clipped_mean:7.3f} +/- {row.rmse_clipped_std:6.3f}  "
            f"MAE={row.mae_clipped_mean:7.3f} +/- {row.mae_clipped_std:6.3f}  "
            f"R2={row.r2_clipped_mean:6.4f} +/- {row.r2_clipped_std:6.4f}"
        )


if __name__ == "__main__":
    main()
