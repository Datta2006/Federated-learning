"""Unit tests for the public preprocessing seams."""

import numpy as np
import pandas as pd
import pytest

from common.preprocess import (
    clean_pm25_series,
    derive_relative_humidity,
    inverse_minmax,
    make_windows,
    minmax_scale,
)


def test_derive_relative_humidity_matches_magnus_formula():
    # TEMP=20 C, DEWP=10 C -> 52.5413... % from the Magnus formula.
    assert derive_relative_humidity(20.0, 10.0) == pytest.approx(52.541325581, rel=1e-9)


def test_derive_relative_humidity_is_clipped_to_physical_range():
    # A dew point above air temperature is unphysical; the result must stay <= 100.
    assert 0.0 <= derive_relative_humidity(10.0, 30.0) <= 100.0
    assert 0.0 <= derive_relative_humidity(-30.0, -60.0) <= 100.0


def test_clean_pm25_series_forward_fills_then_clips():
    values = pd.Series([1.0, np.nan, np.nan, 4.0, 100.0])

    cleaned = clean_pm25_series(values, clip_p995=50.0)

    expected = [1.0, 1.0, 1.0, 4.0, 50.0]
    np.testing.assert_allclose(cleaned.to_numpy(), expected)


def test_clean_pm25_series_forward_fills_before_interpolation():
    # ffill runs first, so an internal gap takes the previous value.
    values = pd.Series([0.0, np.nan, 2.0])

    cleaned = clean_pm25_series(values, clip_p995=100.0)

    np.testing.assert_allclose(cleaned.to_numpy(), [0.0, 0.0, 2.0])


def test_make_windows_returns_expected_sliding_windows_and_targets():
    # Six timesteps and window=3 produce three samples.
    features = np.array(
        [
            [1.0, 10.0],
            [2.0, 20.0],
            [3.0, 30.0],
            [4.0, 40.0],
            [5.0, 50.0],
            [6.0, 60.0],
        ]
    )
    target = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])

    X, y, target_indices = make_windows(features, target, window_hours=3)

    assert X.shape == (3, 3, 2)
    assert y.shape == (3,)
    np.testing.assert_allclose(
        X,
        np.array(
            [
                [[1.0, 10.0], [2.0, 20.0], [3.0, 30.0]],
                [[2.0, 20.0], [3.0, 30.0], [4.0, 40.0]],
                [[3.0, 30.0], [4.0, 40.0], [5.0, 50.0]],
            ]
        ),
    )
    np.testing.assert_allclose(y, [40.0, 50.0, 60.0])
    np.testing.assert_array_equal(target_indices, [3, 4, 5])


def test_minmax_scale_and_inverse_round_trip():
    values = np.array([[10.0, -5.0], [20.0, 5.0]])
    feature_min = np.array([0.0, -10.0])
    feature_max = np.array([100.0, 10.0])

    scaled = minmax_scale(values, feature_min, feature_max)
    restored = inverse_minmax(scaled, feature_min, feature_max)

    np.testing.assert_allclose(scaled, [[0.1, 0.25], [0.2, 0.75]])
    np.testing.assert_allclose(restored, values)


def test_global_scaler_ignores_test_outliers_and_split_is_chronological():
    from common.preprocess import compute_global_scaler, prepare_node_windows

    rows = 20
    frame = pd.DataFrame(
        {
            "year": [2010] * rows,
            "timestamp": pd.date_range("2010-01-01", periods=rows, freq="h"),
            "pm25": list(range(10)) + [1000 + i for i in range(10)],
            "pm2.5": list(range(10)) + [1000 + i for i in range(10)],
            "temp": list(range(rows)),
            "rh": [20 + i for i in range(rows)],
        }
    )
    scaler = compute_global_scaler(
        frame,
        nodes={"node1": 2010},
        features=["pm25", "temp", "rh"],
        train_fraction=0.5,
        clip_quantile=0.995,
    )

    # The held-out 1000+ PM2.5 values must not influence the scaler.
    assert scaler["feature_max"][0] < 10.0

    prepared = prepare_node_windows(
        frame,
        node_id="node1",
        year=2010,
        scaler=scaler,
        features=["pm25", "temp", "rh"],
        window_hours=3,
        train_fraction=0.5,
        val_fraction_of_train=0.1,
    )

    split_timestamp = frame.loc[10, "timestamp"]
    assert prepared["test_timestamps"].min() >= split_timestamp
    assert prepared["test_timestamps"].max() == frame["timestamp"].max()
    assert len(prepared["X_train"]) > 0
    assert len(prepared["X_val"]) > 0
    assert len(prepared["X_test"]) > 0
    # Raw targets preserve the held-out 1000+ values; clipped targets do not.
    assert prepared["y_test_raw"].max() > scaler["pm25_clip"]
    assert prepared["y_test_clipped"].max() <= scaler["pm25_clip"]
    assert prepared["current_test_pm25_raw"][0] == pytest.approx(9.0)
