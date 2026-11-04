"""Local-only baseline: one independent model per node, no weight sharing."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import tensorflow as tf

from baselines.common import (
    aggregate_per_node_results,
    evaluate_targets,
    inverse_pm25,
    load_prepared,
    make_seed_result,
    save_per_node_results,
)
from common.model import build_model, make_callbacks, model_summary, set_seed


def run(
    config_path: str | Path | None = None,
    *,
    epochs: int | None = None,
    verbose: int = 0,
    seed: int | None = None,
) -> dict:
    """Train each node locally and pool predictions for one global score."""
    config, _raw, prepared = load_prepared(config_path)
    model_cfg = config["model"]
    base_seed = int(seed if seed is not None else config["seed"])

    all_prediction: list[np.ndarray] = []
    all_truth_raw: list[np.ndarray] = []
    all_truth_clipped: list[np.ndarray] = []
    per_node: list[dict] = []
    total_train_seconds = 0.0
    epoch_counts: list[int] = []
    parameters = 0

    for index, (node_id, item) in enumerate(prepared.items()):
        tf.keras.backend.clear_session()
        node_seed = base_seed + index
        set_seed(node_seed)
        model = build_model(
            window_hours=int(config["window_hours"]),
            n_features=len(config["features"]),
            conv_filters=int(model_cfg["conv_filters"]),
            kernel_size=int(model_cfg["kernel_size"]),
            pool_size=int(model_cfg["pool_size"]),
            rnn_units=int(model_cfg["rnn_units"]),
            dropout=float(model_cfg["dropout"]),
            learning_rate=float(model_cfg["learning_rate"]),
            seed=node_seed,
        )
        parameters = int(model.count_params())
        print(
            f"{node_id} ({item['year']}): train={len(item['X_train'])} "
            f"val={len(item['X_val'])} test={len(item['X_test'])} "
            f"model={model_summary(model)['parameters']} params seed={node_seed}"
        )

        started = time.perf_counter()
        history = model.fit(
            item["X_train"],
            item["y_train"],
            validation_data=(item["X_val"], item["y_val"]),
            epochs=int(epochs or model_cfg["max_epochs"]),
            batch_size=int(model_cfg["batch_size"]),
            shuffle=True,
            verbose=verbose,
            callbacks=make_callbacks(int(model_cfg["patience"])),
        )
        elapsed = time.perf_counter() - started
        total_train_seconds += elapsed
        epochs_ran = len(history.history["loss"])
        epoch_counts.append(epochs_ran)

        scaled_prediction = model.predict(
            item["X_test"], batch_size=256, verbose=0
        ).reshape(-1)
        prediction = inverse_pm25(scaled_prediction, item)
        metrics = evaluate_targets(
            prediction,
            item["y_test_raw"],
            item["y_test_clipped"],
        )
        all_prediction.append(prediction)
        all_truth_raw.append(item["y_test_raw"])
        all_truth_clipped.append(item["y_test_clipped"])
        per_node.append(
            {
                "node_id": node_id,
                "year": item["year"],
                "seed": node_seed,
                "n_train": len(item["X_train"]),
                "n_test": len(item["X_test"]),
                **metrics,
                "parameters": parameters,
                "epochs": epochs_ran,
                "train_seconds": round(elapsed, 3),
            }
        )
        print(
            f"{node_id}: raw RMSE={metrics['rmse_raw']:.4f} "
            f"MAE={metrics['mae_raw']:.4f} R2={metrics['r2_raw']:.4f} | "
            f"clipped RMSE={metrics['rmse_clipped']:.4f} "
            f"MAE={metrics['mae_clipped']:.4f} R2={metrics['r2_clipped']:.4f} | "
            f"epochs={epochs_ran} seconds={elapsed:.1f}"
        )

    metrics = evaluate_targets(
        np.concatenate(all_prediction),
        np.concatenate(all_truth_raw),
        np.concatenate(all_truth_clipped),
    )
    result = make_seed_result(
        "local_only",
        base_seed,
        n_train=sum(int(row["n_train"]) for row in per_node),
        n_test=len(np.concatenate(all_truth_raw)),
        metrics=metrics,
        parameters=parameters,
        epochs=float(np.mean(epoch_counts)),
        train_seconds=total_train_seconds,
    )
    result["per_node"] = per_node
    print(
        f"local_only seed={base_seed} "
        f"raw RMSE={metrics['rmse_raw']:.4f} MAE={metrics['mae_raw']:.4f} "
        f"R2={metrics['r2_raw']:.4f} | "
        f"clipped RMSE={metrics['rmse_clipped']:.4f} "
        f"MAE={metrics['mae_clipped']:.4f} R2={metrics['r2_clipped']:.4f} | "
        f"seconds={result['train_seconds']:.1f}"
    )
    return result


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run the local-only baseline")
    parser.add_argument("--config", default=None)
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", type=int, default=0, choices=[0, 1, 2])
    args = parser.parse_args()
    result = run(
        args.config,
        epochs=args.epochs,
        verbose=args.verbose,
        seed=args.seed,
    )
    path = save_per_node_results(aggregate_per_node_results(result["per_node"]))
    print(f"saved {path}")


if __name__ == "__main__":
    _main()
