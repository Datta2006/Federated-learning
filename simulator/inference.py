"""Inference Component for Edge Inference (Stack 4).

Loads the CNN-RNN model, runs preprocessing pipeline matching training exactly,
and executes inference for PM2.5 delta-target prediction.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from common.model import build_model_from_config
from common.preprocess import (
    clean_pm25_series,
    fill_pm25_series,
    minmax_scale,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    """Result of a single inference call."""

    pm25_delta_pred: float
    pm25_current: float
    pm25_predicted: float
    timestamp: str
    inference_ms: float
    model_version: int | None


class InferenceComponent:
    """Runs edge inference using the deployed CNN-RNN model.

    - Loads model architecture and weights from ModelDeploymentComponent
    - Applies identical preprocessing as training (fill, clean, scale, cyclic hour)
    - Runs inference on sliding windows of sensor data
    - Returns PM2.5 predictions (current + predicted delta)
    """

    def __init__(
        self,
        gateway_id: str,
        model_deployment: Any,
        window_hours: int = 24,
        horizon: int = 1,
        feature_config: dict[str, Any] | None = None,
        scaler_config: dict[str, Any] | None = None,
    ) -> None:
        self.gateway_id = gateway_id
        self.model_deployment = model_deployment
        self.window_hours = window_hours
        self.horizon = horizon

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

        self._lock = threading.RLock()
        self._model: Any = None
        self._model_version: int | None = None
        self._model_architecture_hash: str | None = None
        self._inference_count = 0
        self._inference_errors = 0
        self._total_inference_ms = 0.0
        self._last_inference_at: float | None = None
        self._last_inference_result: InferenceResult | None = None
        self._history: list[dict[str, Any]] = []
        self._max_history = 1000

    def _ensure_model_loaded(self) -> bool:
        """Load model from deployment component if not loaded or version changed."""
        with self._lock:
            active_version = self.model_deployment.active_version
            active_weights = self.model_deployment.active_weights
            architecture_hash = self.model_deployment._active_architecture_hash

            if (
                active_weights is None
                or active_version is None
                or self._model_version == active_version
            ):
                return self._model is not None

            # Build model architecture
            try:
                n_features = len(self.features) + 2  # +2 for sin/cos hour
                model_config = {
                    "window_hours": self.window_hours,
                    "n_features": n_features,
                    "conv_filters": 64,
                    "kernel_size": 2,
                    "pool_size": 1,
                    "rnn_units": 64,
                    "dropout": 0.2,
                    "learning_rate": 0.001,
                    "seed": 42,
                }
                self._model = build_model_from_config(model_config)
                # Set weights
                self._model.set_weights(active_weights)
                self._model_version = active_version
                self._model_architecture_hash = architecture_hash
                LOGGER.info(
                    "Loaded model version %d on gateway %s", active_version, self.gateway_id
                )
                return True
            except Exception:
                LOGGER.exception("Failed to load model")
                self._model = None
                self._model_version = None
                self._model_architecture_hash = None
                return False

    def preprocess_window(
        self,
        pm25_series: np.ndarray,
        temp_series: np.ndarray,
        rh_series: np.ndarray,
        timestamps: np.ndarray,
    ) -> np.ndarray | None:
        """Preprocess a window of sensor data exactly like training.

        Args:
            pm25_series: Raw PM2.5 values (length window_hours)
            temp_series: Temperature values
            rh_series: Relative humidity values
            timestamps: Timestamps for cyclic hour encoding

        Returns:
            Preprocessed window array of shape (window_hours, n_features) or None on error
        """
        try:
            if len(pm25_series) != self.window_hours:
                return None

            # Fill and clean PM2.5 (matching training exactly)
            # Convert to pandas Series for preprocessing functions
            pm25_series_pd = pd.Series(pm25_series)
            pm25_filled = fill_pm25_series(pm25_series_pd)
            pm25_clean = clean_pm25_series(pm25_filled, self.pm25_clip)

            # Build feature matrix
            features_raw = np.column_stack([pm25_clean.to_numpy(), temp_series, rh_series]).astype(
                np.float32
            )

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

    def infer(
        self,
        pm25_series: np.ndarray,
        temp_series: np.ndarray,
        rh_series: np.ndarray,
        timestamps: np.ndarray,
    ) -> InferenceResult | None:
        """Run inference on a window of sensor data.

        Args:
            pm25_series: Raw PM2.5 values (length window_hours)
            temp_series: Temperature values
            rh_series: Relative humidity values
            timestamps: Timestamps for cyclic hour encoding

        Returns:
            InferenceResult with predicted PM2.5 or None on error
        """
        start_time = time.perf_counter()

        # Ensure model is loaded
        if not self._ensure_model_loaded():
            return None

        # Preprocess
        window = self.preprocess_window(pm25_series, temp_series, rh_series, timestamps)
        if window is None:
            with self._lock:
                self._inference_errors += 1
            return None

        try:
            # Run inference (add batch dimension)
            x = window[np.newaxis, ...]
            delta_pred_scaled = self._model.predict(x, verbose=0)[0, 0]

            # Current PM2.5 (last value in window, scaled)
            pm25_current_scaled = window[-1, 0]
            pm25_current = pm25_current_scaled * (self.pm25_max - self.pm25_min) + self.pm25_min

            # Convert delta prediction back to raw PM2.5
            delta_pred = delta_pred_scaled * (self.pm25_max - self.pm25_min)
            pm25_predicted = pm25_current + delta_pred

            inference_ms = (time.perf_counter() - start_time) * 1000

            result = InferenceResult(
                pm25_delta_pred=float(delta_pred),
                pm25_current=float(pm25_current),
                pm25_predicted=float(pm25_predicted),
                timestamp=str(timestamps[-1]),
                inference_ms=inference_ms,
                model_version=self._model_version,
            )

            with self._lock:
                self._inference_count += 1
                self._total_inference_ms += inference_ms
                self._last_inference_at = time.time()
                self._last_inference_result = result
                self._history.append(
                    {
                        "timestamp": result.timestamp,
                        "pm25_predicted": result.pm25_predicted,
                        "pm25_current": result.pm25_current,
                        "delta_pred": result.pm25_delta_pred,
                        "inference_ms": result.inference_ms,
                        "model_version": result.model_version,
                    }
                )
                if len(self._history) > self._max_history:
                    self._history.pop(0)

            return result
        except Exception:
            LOGGER.exception("Inference failed")
            with self._lock:
                self._inference_errors += 1
            return None

    def infer_batch(
        self,
        windows: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    ) -> list[InferenceResult | None]:
        """Run inference on multiple windows (for efficiency)."""
        return [self.infer(*w) for w in windows]

    def get_stats(self) -> dict[str, Any]:
        """Get component statistics."""
        with self._lock:
            avg_ms = (
                self._total_inference_ms / self._inference_count
                if self._inference_count > 0
                else 0.0
            )
            return {
                "gateway_id": self.gateway_id,
                "model_loaded": self._model is not None,
                "model_version": self._model_version,
                "model_architecture_hash": self._model_architecture_hash,
                "window_hours": self.window_hours,
                "horizon": self.horizon,
                "inference_count": self._inference_count,
                "inference_errors": self._inference_errors,
                "avg_inference_ms": avg_ms,
                "last_inference_at": self._last_inference_at,
                "last_result": (
                    {
                        "pm25_predicted": self._last_inference_result.pm25_predicted,
                        "pm25_current": self._last_inference_result.pm25_current,
                        "delta_pred": self._last_inference_result.pm25_delta_pred,
                        "timestamp": self._last_inference_result.timestamp,
                        "inference_ms": self._last_inference_result.inference_ms,
                    }
                    if self._last_inference_result
                    else None
                ),
            }

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for monitoring."""
        with self._lock:
            return {
                "component": "InferenceComponent",
                "gateway_id": self.gateway_id,
                "stats": self.get_stats(),
                "recent_history": self._history[-50:],
            }

    def get_recent_predictions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent predictions for dashboard."""
        with self._lock:
            return self._history[-limit:]


__all__ = ["InferenceComponent", "InferenceResult"]