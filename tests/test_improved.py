"""Unit tests for the improved (delta / horizon / cyclic-hour) window seam."""

import numpy as np
import pandas as pd
import pytest

from common.improved import prepare_improved_node, reconstruct_pm25


def _frame(rows: int = 12) -> pd.DataFrame:
    pm = np.arange(rows, dtype=float) * 10.0
    return pd.DataFrame(
        {
            "year": [2010] * rows,
            "timestamp": pd.date_range("2010-01-01", periods=rows, freq="h"),
            "pm2.5": pm,
            "pm25": pm,
            "temp": np.linspace(0.0, 11.0, rows),
            "rh": np.linspace(20.0, 80.0, rows),
        }
    )


def _scaler() -> dict:
    return {
        "feature_min": [0.0, 0.0, 0.0],
        "feature_max": [200.0, 100.0, 100.0],
        "pm25_clip": 1000.0,
    }


def _prepare(**overrides):
    options = {
        "node_id": "node1",
        "year": 2010,
        "scaler": _scaler(),
        "features": ["pm25", "temp", "rh"],
        "window_hours": 2,
        "horizon": 1,
        "delta": True,
        "cyclic_hour": False,
        "train_fraction": 0.8,
        "val_fraction_of_train": 0.1,
    }
    options.update(overrides)
    return prepare_improved_node(_frame(), **options)


def test_delta_targets_reconstruct_the_clipped_future_value():
    prepared = _prepare(delta=True)

    # Feeding the true delta back through the reconstruction seam must recover
    # the future clipped target exactly (up to float32 scaling round-off).
    reconstructed = reconstruct_pm25(prepared["y_test"], prepared)

    np.testing.assert_allclose(
        reconstructed, prepared["y_test_clipped"], rtol=1e-6, atol=1e-5
    )


def test_value_targets_reconstruct_without_adding_the_current_value():
    prepared = _prepare(delta=False)

    reconstructed = reconstruct_pm25(prepared["y_test"], prepared)

    np.testing.assert_allclose(
        reconstructed, prepared["y_test_clipped"], rtol=1e-6, atol=1e-5
    )


def test_horizon_selects_the_target_hours_ahead_not_the_next_hour():
    prepared = _prepare(
        window_hours=2,
        horizon=3,
        delta=False,
        train_fraction=0.5,
        val_fraction_of_train=0.0,
    )

    # y index = i + window - 1 + horizon; with split_row=6 the first test
    # target index is 6, i.e. the timestamp at row 6 and pm25 60.
    assert prepared["test_timestamps"][0] == pd.Timestamp("2010-01-01 06:00")
    assert prepared["y_test_raw"][0] == pytest.approx(60.0)


def test_cyclic_hour_features_are_appended_after_scaled_features():
    prepared = _prepare(window_hours=2, cyclic_hour=True)

    assert prepared["X_train"].shape[-1] == 5
    first_window = prepared["X_train"][0]
    hours = np.array([0, 1])
    expected = np.stack(
        [np.sin(2 * np.pi * hours / 24.0), np.cos(2 * np.pi * hours / 24.0)],
        axis=1,
    )
    np.testing.assert_allclose(first_window[:, -2:], expected, atol=1e-6)


def test_train_targets_strictly_precede_the_test_split():
    prepared = _prepare(
        window_hours=3, horizon=4, delta=True, train_fraction=0.7
    )

    split = pd.Timestamp("2010-01-01 08:00")
    assert prepared["test_timestamps"].min() >= split
    assert prepared["train_timestamps"].max() < split


def test_persistence_prediction_uses_the_last_input_hour():
    prepared = _prepare(window_hours=2, horizon=1, delta=True)

    np.testing.assert_allclose(
        prepared["current_test_pm25_raw"], [80.0, 90.0, 100.0]
    )
