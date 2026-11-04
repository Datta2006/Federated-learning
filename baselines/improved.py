"""Improved-variant baselines: delta target, longer window, no pooling, hour.

Run the full suite (3 seeds) and upsert into results.csv:

    python -m baselines.improved

Quick smoke test (single seed, one epoch, still real data):

    python -m baselines.improved --seeds 42 --epochs 1 --verbose 0 --no-write
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

import numpy as np
import tensorflow as tf

from baselines.common import (
    aggregate_seed_results,
    evaluate_targets,
    make_seed_result,
    plot_results,
    save_aggregate_results,
)
from common.config import load_config, resolve_path
from common.improved import prepare_improved_nodes, reconstruct_pm25
from common.model import build_model, make_callbacks, model_summary, set_seed
from common.preprocess import load_raw


def _load(config_path: str | Path | None) -> tuple[dict[str, Any], Any]:
    config = load_config(config_path)
    raw = load_raw(resolve_path(config["dataset_path"]))
    return config, raw


def _concat(prepared: dict[str, dict[str, Any]], key: str) -> np.ndarray:
    return np.concatenate([item[key] for item in prepared.values()])


def _build(config: dict[str, Any], prepared: dict[str, Any], seed: int, pool_size: int):
    model_cfg = config["model"]
    return build_model(
        window_hours=int(prepared["window_hours"]),
        n_features=int(prepared["n_features"]),
        conv_filters=int(model_cfg["conv_filters"]),
        kernel_size=int(model_cfg["kernel_size"]),
        pool_size=pool_size,
        rnn_units=int(model_cfg["rnn_units"]),
        dropout=float(model_cfg["dropout"]),
        learning_rate=float(model_cfg["learning_rate"]),
        seed=seed,
    )


def _fit(
    config: dict[str, Any],
    model,
    X_train,
    y_train,
    X_val,
    y_val,
    epochs,
    verbose,
):
    model_cfg = config["model"]
    started = time.perf_counter()
    history = model.fit(
        X_train,
        y_train,
        validation_data=(X_val, y_val),
        epochs=int(epochs or model_cfg["max_epochs"]),
        batch_size=int(model_cfg["batch_size"]),
        shuffle=True,
        verbose=verbose,
        callbacks=make_callbacks(int(model_cfg["patience"])),
    )
    return history, time.perf_counter() - started


def run_centralized_improved(
    config_path: str | Path | None = None,
    *,
    window_hours: int = 12,
    horizon: int = 1,
    delta: bool = True,
    cyclic_hour: bool = True,
    pool_size: int = 1,
    epochs: int | None = None,
    verbose: int = 1,
    seed: int | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """Train one improved model on all nodes and score pooled test predictions."""
    config, raw = _load(config_path)
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=window_hours,
        horizon=horizon,
        delta=delta,
        cyclic_hour=cyclic_hour,
    )
    run_seed = int(seed if seed is not None else config["seed"])
    set_seed(run_seed)

    X_train = _concat(prepared, "X_train")
    y_train = _concat(prepared, "y_train")
    X_val = _concat(prepared, "X_val")
    y_val = _concat(prepared, "y_val")
    first = next(iter(prepared.values()))
    model = _build(config, first, run_seed, pool_size)
    method_name = method or (
        f"centralized_improved_w{window_hours}"
        + (f"_h{horizon}" if horizon != 1 else "")
    )
    print(
        f"{method_name}: {model_summary(model)} seed={run_seed} "
        f"train={len(X_train)} val={len(X_val)} test={first['X_test'].shape[0]}"
    )

    history, train_seconds = _fit(
        config, model, X_train, y_train, X_val, y_val, epochs, verbose
    )

    predictions = []
    for item in prepared.values():
        scaled = model.predict(item["X_test"], batch_size=256, verbose=0).reshape(-1)
        predictions.append(reconstruct_pm25(scaled, item))
    prediction = np.concatenate(predictions)

    metrics = evaluate_targets(
        prediction,
        _concat(prepared, "y_test_raw"),
        _concat(prepared, "y_test_clipped"),
    )
    result = make_seed_result(
        method_name,
        run_seed,
        n_train=len(X_train),
        n_test=len(prediction),
        metrics=metrics,
        parameters=int(model.count_params()),
        epochs=len(history.history["loss"]),
        train_seconds=train_seconds,
    )
    print(
        f"{method_name} seed={run_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f} | clipped RMSE={metrics['rmse_clipped']:.4f} "
        f"epochs={result['epochs']} seconds={result['train_seconds']:.1f}"
    )
    return result


def run_local_only_improved(
    config_path: str | Path | None = None,
    *,
    window_hours: int = 12,
    horizon: int = 1,
    delta: bool = True,
    cyclic_hour: bool = True,
    pool_size: int = 1,
    epochs: int | None = None,
    verbose: int = 1,
    seed: int | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """Train one improved model per node, sharing nothing, and pool predictions."""
    config, raw = _load(config_path)
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=window_hours,
        horizon=horizon,
        delta=delta,
        cyclic_hour=cyclic_hour,
    )
    base_seed = int(seed if seed is not None else config["seed"])
    method_name = method or (
        f"local_only_improved_w{window_hours}"
        + (f"_h{horizon}" if horizon != 1 else "")
    )

    predictions: list[np.ndarray] = []
    epoch_counts: list[int] = []
    total_seconds = 0.0
    parameters = 0
    n_train = 0

    for index, (node_id, item) in enumerate(prepared.items()):
        tf.keras.backend.clear_session()
        node_seed = base_seed + index
        set_seed(node_seed)
        model = _build(config, item, node_seed, pool_size)
        parameters = int(model.count_params())
        print(
            f"{method_name} {node_id} ({item['year']}): "
            f"train={len(item['X_train'])} val={len(item['X_val'])} "
            f"test={len(item['X_test'])} seed={node_seed}"
        )
        history, elapsed = _fit(
            config,
            model,
            item["X_train"],
            item["y_train"],
            item["X_val"],
            item["y_val"],
            epochs,
            verbose,
        )
        epoch_counts.append(len(history.history["loss"]))
        total_seconds += elapsed
        n_train += len(item["X_train"])
        scaled = model.predict(item["X_test"], batch_size=256, verbose=0).reshape(-1)
        predictions.append(reconstruct_pm25(scaled, item))

    prediction = np.concatenate(predictions)
    metrics = evaluate_targets(
        prediction,
        _concat(prepared, "y_test_raw"),
        _concat(prepared, "y_test_clipped"),
    )
    result = make_seed_result(
        method_name,
        base_seed,
        n_train=n_train,
        n_test=len(prediction),
        metrics=metrics,
        parameters=parameters,
        epochs=float(np.mean(epoch_counts)),
        train_seconds=total_seconds,
    )
    print(
        f"{method_name} seed={base_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f} | clipped RMSE={metrics['rmse_clipped']:.4f} "
        f"seconds={result['train_seconds']:.1f}"
    )
    return result


def run_persistence_improved(
    config_path: str | Path | None = None,
    *,
    window_hours: int = 12,
    horizon: int = 1,
    seed: int | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    """Persistence on the exact same test windows as the improved model."""
    config, raw = _load(config_path)
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=window_hours,
        horizon=horizon,
        delta=False,
        cyclic_hour=False,
    )
    run_seed = int(seed if seed is not None else config["seed"])
    prediction = _concat(prepared, "current_test_pm25_raw")
    metrics = evaluate_targets(
        prediction,
        _concat(prepared, "y_test_raw"),
        _concat(prepared, "y_test_clipped"),
    )
    method_name = method or (
        f"persistence_w{window_hours}" + (f"_h{horizon}" if horizon != 1 else "")
    )
    result = make_seed_result(
        method_name,
        run_seed,
        n_train=0,
        n_test=len(prediction),
        metrics=metrics,
        parameters=0,
        epochs=0.0,
        train_seconds=0.0,
    )
    print(
        f"{method_name} seed={run_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f}"
    )
    return result


def _parse_seeds(value: str | None, config: dict[str, Any]) -> list[int]:
    if value:
        return [int(part.strip()) for part in value.split(",") if part.strip()]
    configured = config.get("seeds")
    if isinstance(configured, list) and configured:
        return [int(seed) for seed in configured]
    base = int(config["seed"])
    return [base, base + 1, base + 2]


def _parse_windows(value: str) -> list[int]:
    windows = [int(part.strip()) for part in value.split(",") if part.strip()]
    if not windows or any(window < 1 for window in windows):
        raise ValueError("--windows must contain positive integers")
    return windows


def _notes(
    *,
    mode: str,
    window_hours: int,
    horizon: int,
    local: bool,
    delta: bool,
    cyclic_hour: bool,
) -> str:
    if mode == "persistence":
        scope = "Persistence baseline on the same test windows; no learned model"
        variant = "No delta target, no pooling, no hour features."
    else:
        scope = (
            "Five independent per-node models, no sharing"
            if local
            else "One model on pooled first-80% windows of all node-years"
        )
        parts = ["delta target" if delta else "value target", "maxpool=1"]
        parts.append("hour sin/cos" if cyclic_hour else "no hour features")
        variant = "Improved variant: " + ", ".join(parts) + "."
    return (
        f"{scope}. {variant} window={window_hours}h, horizon={horizon}h. "
        "Mean/std over seeds. Raw = filled but unclipped targets; "
        "clipped = p99.5 targets. Headline = raw_unclipped."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run improved-variant baselines")
    parser.add_argument("--config", default=None)
    parser.add_argument("--seeds", default=None, help="comma-separated seeds")
    parser.add_argument("--windows", default="12,24")
    parser.add_argument("--local-windows", default="12")
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--verbose", type=int, default=1, choices=[0, 1, 2])
    parser.add_argument("--no-delta", action="store_true")
    parser.add_argument("--no-cyclic-hour", action="store_true")
    parser.add_argument("--skip-centralized", action="store_true")
    parser.add_argument("--skip-local", action="store_true")
    parser.add_argument("--skip-horizon", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    seeds = _parse_seeds(args.seeds, config)
    windows = _parse_windows(args.windows)
    delta = not args.no_delta
    cyclic_hour = not args.no_cyclic_hour
    print(f"seeds: {seeds} windows: {windows} delta={delta} hour={cyclic_hour}")

    aggregate_rows: list[dict[str, Any]] = []
    all_seed_rows: list[dict[str, Any]] = []

    def record(
        method: str,
        rows: list[dict[str, Any]],
        *,
        mode: str,
        window: int,
        horizon: int,
        local: bool = False,
    ) -> None:
        all_seed_rows.extend(rows)
        notes = _notes(
            mode=mode,
            window_hours=window,
            horizon=horizon,
            local=local,
            delta=delta,
            cyclic_hour=cyclic_hour,
        )
        aggregate_rows.append(aggregate_seed_results(method, rows, notes))

    if not args.skip_centralized:
        for window in windows:
            method = f"centralized_improved_w{window}"
            rows = [
                run_centralized_improved(
                    args.config,
                    window_hours=window,
                    horizon=1,
                    delta=delta,
                    cyclic_hour=cyclic_hour,
                    epochs=args.epochs,
                    verbose=args.verbose,
                    seed=seed,
                    method=method,
                )
                for seed in seeds
            ]
            record(method, rows, mode="model", window=window, horizon=1)

            persistence = f"persistence_w{window}"
            rows = [
                run_persistence_improved(
                    args.config,
                    window_hours=window,
                    horizon=1,
                    seed=seed,
                    method=persistence,
                )
                for seed in seeds
            ]
            record(persistence, rows, mode="persistence", window=window, horizon=1)

    if not args.skip_local:
        for window in _parse_windows(args.local_windows):
            method = f"local_only_improved_w{window}"
            rows = [
                run_local_only_improved(
                    args.config,
                    window_hours=window,
                    horizon=1,
                    delta=delta,
                    cyclic_hour=cyclic_hour,
                    epochs=args.epochs,
                    verbose=args.verbose,
                    seed=seed,
                    method=method,
                )
                for seed in seeds
            ]
            record(method, rows, mode="model", window=window, horizon=1, local=True)

    if not args.skip_horizon:
        method = f"centralized_improved_w12_h{args.horizon}"
        rows = [
            run_centralized_improved(
                args.config,
                window_hours=12,
                horizon=args.horizon,
                delta=delta,
                cyclic_hour=cyclic_hour,
                epochs=args.epochs,
                verbose=args.verbose,
                seed=seed,
                method=method,
            )
            for seed in seeds
        ]
        record(method, rows, mode="model", window=12, horizon=args.horizon)

        persistence = f"persistence_w12_h{args.horizon}"
        rows = [
            run_persistence_improved(
                args.config,
                window_hours=12,
                horizon=args.horizon,
                seed=seed,
                method=persistence,
            )
            for seed in seeds
        ]
        record(persistence, rows, mode="persistence", window=12, horizon=args.horizon)

    if args.no_write:
        print("--no-write set; results not saved")
        return

    results_path, seed_path = save_aggregate_results(
        config, aggregate_rows, all_seed_rows
    )
    print(f"saved {results_path} and {seed_path}")
    print(f"saved {plot_results(config)}")


if __name__ == "__main__":
    main()
