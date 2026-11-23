"""Forecasting Component for Edge Inference (Stack 4).

Generates configurable PM2.5 forecasts using the deployed CNN-RNN model
and evaluates against WHO Air Quality Guidelines thresholds.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from common.model import build_model_from_config
from common.preprocess import clean_pm25_series, fill_pm25_series, minmax_scale

LOGGER = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Result of a single forecast call."""

    pm25_forecast: list[float]  # Forecasted PM2.5 values for each horizon step
    pm25_current: float  # Current PM2.5 (last value in window)
    horizon: int  # Number of steps forecasted
    thresholds_crossed: list[dict[str, Any]]  # WHO AQI threshold crossings
    timestamp: str  # Timestamp of the forecast
    inference_ms: float  # Time taken for inference
    model_version: int | None


# WHO Air Quality Guidelines for PM2.5 (µg/m³)
WHO_PM25_THRESHOLDS = {
    "good": 5.0,        # WHO 2021 guideline: annual mean ≤ 5 µg/m³
    "moderate": 15.0,   # Interim target 1
    "unhealthy_sensitive": 25.0,  # Interim target 2 (24-hour)
    "unhealthy": 37.5,  # Interim target 3
    "very_unhealthy": 50.0,       # Interim target 4
    "hazardous": 75.0,  # Above this is hazardous
}


class ForecastingComponent:
    """Generates PM2.5 forecasts using the deployed CNN-RNN model.

    - Uses InferenceComponent internally for single-step predictions
    - Supports multi-horizon forecasting via recursive prediction
    - Evaluates forecasts against WHO AQI thresholds
    - Provides configurable alert thresholds
    """

    def __init__(
        self,
        gateway_id: str,
        inference_component: Any,  # InferenceComponent instance
        model_deployment: Any,  # ModelDeploymentComponent instance
        window_hours: int = 24,
        default_horizon: int = 6,
        feature_config: dict[str, Any] | None = None,
        scaler_config: dict[str, Any] | None = None,
        alert_thresholds: dict[str, float] | None = None,
    ) -> None:
        self.gateway_id = gateway_id
        self.inference_component = inference_component
        self.model_deployment = model_deployment
        self.window_hours = window_hours
        self.default_horizon = default_horizon

        # Preprocessing config (must match training exactly)
        self.features = feature_config.get("features", ["pm25", "temp", "rh"]) if feature_config else ["pm25", "temp", "rh"]
        self.pm25_clip = scaler_config.get("pm25_clip", 300.0) if scaler_config else 300.0
        self.feature_min = np.array(
            scaler_config.get("feature_min", [0.0, -10.0, 0.0]), dtype=np.float32
        ) if scaler_config else np.array([0.0, -10.0, 0.0], dtype=np.float32)
        self.feature_max = np.array(
            scaler_config.get("feature_max", [300.0, 60.0, 100.0]), dtype=np.float32
        ) if scaler_config else np.array([300.0, 60.0, 100.0], dtype=np.float32)
        self.pm25_min = float(self.feature_min[0])
        self.pm25_max = float(self.feature_max[0])

        # Alert thresholds (default to WHO AQI guidelines)
        self.alert_thresholds = alert_thresholds or WHO_PM25_THRESHOLDS.copy()

        self._lock = threading.RLock()
        self._forecast_count = 0
        self._forecast_errors = 0
        self._total_forecast_ms = 0.0
        self._last_forecast_at: float | None = None
        self._last_forecast_result: ForecastResult | None = None
        self._history: list[dict[str, Any]] = []
        self._max_history = 500

    def _preprocess_window(
        self,
        pm25_series: np.ndarray,
        temp_series: np.ndarray,
        rh_series: np.ndarray,
        timestamps: np.ndarray,
    ) -> np.ndarray | None:
        """Preprocess a window of sensor data exactly like training."""
        try:
            if len(pm25_series) != self.window_hours:
                return None

            # Fill and clean PM2.5 (matching training exactly)
            # Convert to pandas Series for preprocessing functions
            pm25_series_pd = pd.Series(pm25_series)
            pm25_filled = fill_pm25_series(pm25_series_pd)
            pm25_clean = clean_pm25_series(pm25_filled, self.pm25_clip)

            # Build feature matrix
            features_raw = np.column_stack([pm25_clean.to_numpy(), temp_series, rh_series]).astype(np.float32)

            # Min-max scale
            scaled = minmax_scale(features_raw, self.feature_min, self.feature_max)

            # Cyclic hour encoding
            hours = np.array([ts.astype("datetime64[h]").astype(int) % 24 for ts in timestamps], dtype=np.float32)
            angle = 2.0 * np.pi * hours / 24.0
            scaled = np.hstack(
                [scaled, np.sin(angle)[:, None], np.cos(angle)[:, None]]
            ).astype(np.float32)

            return scaled
        except Exception:
            LOGGER.exception("Preprocessing failed")
            return None

    def _check_thresholds(self, pm25_values: list[float]) -> list[dict[str, Any]]:
        """Check which WHO AQI thresholds are crossed in the forecast."""
        crossed = []
        for i, value in enumerate(pm25_values):
            for threshold_name, threshold_value in self.alert_thresholds.items():
                if value >= threshold_value:
                    crossed.append({
                        "step": i + 1,
                        "threshold": threshold_name,
                        "threshold_value": threshold_value,
                        "forecast_value": float(value),
                        "exceeded_by": float(value - threshold_value),
                    })
        return crossed

    def forecast(
        self,
        pm25_series: np.ndarray,
        temp_series: np.ndarray,
        rh_series: np.ndarray,
        timestamps: np.ndarray,
        horizon: int | None = None,
    ) -> ForecastResult | None:
        """Generate multi-horizon PM2.5 forecast using recursive prediction.

        Args:
            pm25_series: Raw PM2.5 values (length window_hours)
            temp_series: Temperature values
            rh_series: Relative humidity values
            timestamps: Timestamps for cyclic hour encoding
            horizon: Number of steps to forecast (default: default_horizon)

        Returns:
            ForecastResult with predicted PM2.5 values and threshold analysis
        """
        start_time = time.perf_counter()
        horizon = horizon or self.default_horizon

        # Ensure model is loaded via inference component
        if not self.inference_component._ensure_model_loaded():
            return None

        # Initial preprocessing
        window = self._preprocess_window(pm25_series, temp_series, rh_series, timestamps)
        if window is None:
            with self._lock:
                self._forecast_errors += 1
            return None

        try:
            # Get model from inference component
            model = self.inference_component._model
            if model is None:
                return None

            # Recursive multi-step forecasting
            pm25_forecast = []
            current_window = window.copy()
            current_pm25_raw = pm25_series.copy()
            current_temp = temp_series.copy()
            current_rh = rh_series.copy()
            current_timestamps = timestamps.copy()

            for step in range(horizon):
                # Run inference on current window
                x = current_window[np.newaxis, ...]
                delta_pred_scaled = model.predict(x, verbose=0)[0, 0]

                # Current PM2.5 (last value in window, scaled)
                pm25_current_scaled = current_window[-1, 0]
                pm25_current = pm25_current_scaled * (self.pm25_max - self.pm25_min) + self.pm25_min

                # Convert delta prediction back to raw PM2.5
                delta_pred = delta_pred_scaled * (self.pm25_max - self.pm25_min)
                pm25_predicted = pm25_current + delta_pred

                pm25_forecast.append(float(pm25_predicted))

                # Update window for next step (roll and add new prediction)
                # We need to estimate next temp/rh - use last known values for simplicity
                # In production, this could use a weather forecast
                new_pm25_scaled = (pm25_predicted - self.pm25_min) / (self.pm25_max - self.pm25_min)
                new_pm25_scaled = np.clip(new_pm25_scaled, 0.0, 1.0)

                # Roll window
                current_window = np.roll(current_window, -1, axis=0)
                current_window[-1, 0] = new_pm25_scaled  # PM2.5
                # Keep temp/rh same (last known values)
                # Update cyclic hour encoding
                next_hour = (current_timestamps[-1].astype("datetime64[h]").astype(int) + 1) % 24
                angle = 2.0 * np.pi * next_hour / 24.0
                current_window[-1, -2] = np.sin(angle)
                current_window[-1, -1] = np.cos(angle)

                # Update timestamps
                next_ts = current_timestamps[-1] + np.timedelta64(1, 'h')
                current_timestamps = np.roll(current_timestamps, -1)
                current_timestamps[-1] = next_ts

            inference_ms = (time.perf_counter() - start_time) * 1000

            # Get current PM2.5 (last actual value)
            pm25_current_scaled = window[-1, 0]
            pm25_current = float(pm25_current_scaled * (self.pm25_max - self.pm25_min) + self.pm25_min)

            # Check thresholds
            thresholds_crossed = self._check_thresholds(pm25_forecast)

            result = ForecastResult(
                pm25_forecast=pm25_forecast,
                pm25_current=pm25_current,
                horizon=horizon,
                thresholds_crossed=thresholds_crossed,
                timestamp=str(timestamps[-1]),
                inference_ms=inference_ms,
                model_version=self.inference_component._model_version,
            )

            with self._lock:
                self._forecast_count += 1
                self._total_forecast_ms += inference_ms
                self._last_forecast_at = time.time()
                self._last_forecast_result = result
                self._history.append({
                    "timestamp": result.timestamp,
                    "pm25_forecast": result.pm25_forecast,
                    "pm25_current": result.pm25_current,
                    "horizon": result.horizon,
                    "thresholds_crossed": result.thresholds_crossed,
                    "inference_ms": result.inference_ms,
                    "model_version": result.model_version,
                })
                if len(self._history) > self._max_history:
                    self._history.pop(0)

            return result

        except Exception:
            LOGGER.exception("Forecasting failed")
            with self._lock:
                self._forecast_errors += 1
            return None

    def forecast_batch(
        self,
        windows: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
        horizon: int | None = None,
    ) -> list[ForecastResult | None]:
        """Generate forecasts for multiple windows."""
        return [self.forecast(*w, horizon=horizon) for w in windows]

    def get_stats(self) -> dict[str, Any]:
        """Get component statistics."""
        with self._lock:
            avg_ms = (
                self._total_forecast_ms / self._forecast_count
                if self._forecast_count > 0
                else 0.0
            )
            return {
                "gateway_id": self.gateway_id,
                "model_loaded": self.inference_component._model is not None,
                "model_version": self.inference_component._model_version,
                "window_hours": self.window_hours,
                "default_horizon": self.default_horizon,
                "forecast_count": self._forecast_count,
                "forecast_errors": self._forecast_errors,
                "avg_forecast_ms": avg_ms,
                "last_forecast_at": self._last_forecast_at,
                "alert_thresholds": self.alert_thresholds,
                "last_result": (
                    {
                        "pm25_forecast": self._last_forecast_result.pm25_forecast,
                        "pm25_current": self._last_forecast_result.pm25_current,
                        "horizon": self._last_forecast_result.horizon,
                        "thresholds_crossed": self._last_forecast_result.thresholds_crossed,
                        "timestamp": self._last_forecast_result.timestamp,
                        "inference_ms": self._last_forecast_result.inference_ms,
                    }
                    if self._last_forecast_result
                    else None
                ),
            }

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for monitoring."""
        with self._lock:
            return {
                "component": "ForecastingComponent",
                "gateway_id": self.gateway_id,
                "stats": self.get_stats(),
                "recent_history": self._history[-20:],
            }

    def get_recent_forecasts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent forecasts for dashboard."""
        with self._lock:
            return self._history[-limit:]


__all__ = ["ForecastingComponent", "ForecastResult", "WHO_PM25_THRESHOLDS"]