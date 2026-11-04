"""Hand-computed sanity check for the baseline metric seam."""

import numpy as np
import pandas as pd
import pytest

from baselines.common import evaluate_metrics


def test_evaluate_metrics_matches_hand_computed_values():
    y_true = np.array([3.0, -0.5, 2.0, 7.0])
    y_pred = np.array([2.5, 0.0, 2.0, 8.0])

    metrics = evaluate_metrics(y_true, y_pred)

    assert metrics["mae"] == pytest.approx(0.5)
    assert metrics["rmse"] == pytest.approx(np.sqrt(0.375))
    assert metrics["r2"] == pytest.approx(1.0 - 1.5 / 29.1875)


def test_evaluate_metrics_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="same length"):
        evaluate_metrics([1.0, 2.0], [1.0])


def test_evaluate_targets_reports_raw_and_clipped_scores():
    from baselines.common import evaluate_targets

    prediction = np.array([10.0, 20.0, 30.0])
    raw = np.array([10.0, 25.0, 30.0])
    clipped = np.array([10.0, 20.0, 30.0])

    metrics = evaluate_targets(prediction, raw, clipped)

    assert metrics["mae_raw"] == pytest.approx(5.0 / 3.0)
    assert metrics["mae_clipped"] == pytest.approx(0.0)
    assert metrics["rmse_raw"] > 0.0
    assert metrics["rmse_clipped"] == pytest.approx(0.0)


def test_aggregate_seed_results_reports_mean_and_sample_std():
    from baselines.common import aggregate_seed_results

    seed_rows = []
    for seed, rmse in [(42, 1.0), (43, 2.0), (44, 3.0)]:
        seed_rows.append(
            {
                "method": "toy",
                "seed": seed,
                "n_train": 10,
                "n_test": 5,
                "rmse_raw": rmse,
                "mae_raw": rmse,
                "r2_raw": 0.5,
                "rmse_clipped": rmse + 1.0,
                "mae_clipped": rmse + 1.0,
                "r2_clipped": 0.6,
                "parameters": 100,
                "epochs": 2,
                "train_seconds": 1.0,
            }
        )

    aggregate = aggregate_seed_results("toy", seed_rows, "note")

    assert aggregate["n_seeds"] == 3
    assert aggregate["seeds"] == "42,43,44"
    assert aggregate["rmse_raw_mean"] == pytest.approx(2.0)
    assert aggregate["rmse_raw_std"] == pytest.approx(1.0)
    assert aggregate["headline"] == "raw_unclipped"


def test_save_aggregate_results_replaces_stale_seed_rows(tmp_path):
    from baselines.common import aggregate_seed_results, save_aggregate_results

    config = {"paths": {"results_csv": str(tmp_path / "results.csv")}}

    def row(seed):
        return {
            "method": "toy",
            "seed": seed,
            "n_train": 10,
            "n_test": 5,
            "rmse_raw": 1.0,
            "mae_raw": 1.0,
            "r2_raw": 0.5,
            "rmse_clipped": 2.0,
            "mae_clipped": 2.0,
            "r2_clipped": 0.4,
            "parameters": 100,
            "epochs": 1,
            "train_seconds": 0.1,
        }

    three = [row(seed) for seed in (42, 43, 44)]
    save_aggregate_results(
        config,
        [aggregate_seed_results("toy", three, "three seeds")],
        three,
    )
    one = [row(42)]
    save_aggregate_results(
        config,
        [aggregate_seed_results("toy", one, "one seed")],
        one,
    )

    seeds = pd.read_csv(tmp_path / "results_by_seed.csv")
    aggregate = pd.read_csv(tmp_path / "results.csv")
    assert seeds["seed"].tolist() == [42]
    assert aggregate.loc[0, "n_seeds"] == 1
