"""PM2.5-only ablation: same pipeline with temperature and humidity removed."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

from baselines.common import (
    evaluate_targets,
    inverse_pm25,
    load_prepared,
    make_seed_result,
)
from common.model import build_model, make_callbacks, model_summary, set_seed


def _select_pm25(features: np.ndarray, pm25_index: int) -> np.ndarray:
    return features[:, :, pm25_index : pm25_index + 1]


def run(
    config_path: str | Path | None = None,
    *,
    epochs: int | None = None,
    verbose: int = 2,
    seed: int | None = None,
) -> dict:
    """Train the same model on PM2.5 alone and compare with the full ablation."""
    config, _raw, prepared = load_prepared(config_path)
    model_cfg = config["model"]
    run_seed = int(seed if seed is not None else config["seed"])
    pm25_index = list(config["features"]).index("pm25")
    set_seed(run_seed)

    X_train = _select_pm25(
        np.concatenate([item["X_train"] for item in prepared.values()]), pm25_index
    )
    y_train = np.concatenate([item["y_train"] for item in prepared.values()])
    X_val = _select_pm25(
        np.concatenate([item["X_val"] for item in prepared.values()]), pm25_index
    )
    y_val = np.concatenate([item["y_val"] for item in prepared.values()])
    X_test = _select_pm25(
        np.concatenate([item["X_test"] for item in prepared.values()]), pm25_index
    )
    y_test_raw = np.concatenate([item["y_test_raw"] for item in prepared.values()])
    y_test_clipped = np.concatenate(
        [item["y_test_clipped"] for item in prepared.values()]
    )

    model = build_model(
        window_hours=int(config["window_hours"]),
        n_features=1,
        conv_filters=int(model_cfg["conv_filters"]),
        kernel_size=int(model_cfg["kernel_size"]),
        pool_size=int(model_cfg["pool_size"]),
        rnn_units=int(model_cfg["rnn_units"]),
        dropout=float(model_cfg["dropout"]),
        learning_rate=float(model_cfg["learning_rate"]),
        seed=run_seed,
    )
    print(f"pm25_only model: {model_summary(model)} seed={run_seed}")
    print(f"train={len(X_train)} val={len(X_val)} test={len(X_test)}")

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
    train_seconds = time.perf_counter() - started

    scaled_prediction = model.predict(X_test, batch_size=256, verbose=0).reshape(-1)
    shared_bounds = next(iter(prepared.values()))
    prediction = inverse_pm25(scaled_prediction, shared_bounds)
    metrics = evaluate_targets(prediction, y_test_raw, y_test_clipped)

    result = make_seed_result(
        "pm25_only",
        run_seed,
        n_train=len(X_train),
        n_test=len(X_test),
        metrics=metrics,
        parameters=int(model.count_params()),
        epochs=len(history.history["loss"]),
        train_seconds=train_seconds,
    )
    print(
        f"pm25_only seed={run_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f} | "
        f"clipped RMSE={metrics['rmse_clipped']:.4f} "
        f"MAE={metrics['mae_clipped']:.4f} R2={metrics['r2_clipped']:.4f} | "
        f"epochs={result['epochs']} seconds={result['train_seconds']:.1f}"
    )
    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the PM2.5-only ablation")
    parser.add_argument("--config", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", type=int, default=2, choices=[0, 1, 2])
    args = parser.parse_args()
    run(args.config, epochs=args.epochs, verbose=args.verbose, seed=args.seed)


if __name__ == "__main__":
    _main()
