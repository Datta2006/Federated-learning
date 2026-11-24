"""Demo model prediction endpoint for the Testing Model Lab.

This provides a simple demonstration of model inference using:
1. Mock model weights that produce deterministic predictions
2. Random input generation for demos
3. A simple linear model for demonstration purposes

The endpoint returns predictions without requiring TensorFlow, making it
useful for demos and API testing.
"""

from __future__ import annotations

import random
import time
from typing import Any

import numpy as np


def _linear_predict(weights: np.ndarray, input_data: np.ndarray) -> np.ndarray:
    """Simple linear model prediction: y = weights @ x + bias."""
    if len(weights) == 0:
        return np.array([0.5])
    
    # Use first n weights for input features, bias is the last
    n_features = min(len(input_data), len(weights) - 1)
    if n_features == 0:
        return np.array([weights[0]]) if len(weights) > 0 else np.array([0.5])
    
    # Linear combination + bias
    prediction = float(np.dot(weights[:n_features], input_data[:n_features]))
    if len(weights) > n_features:
        prediction += float(weights[n_features])  # bias
    
    return np.array([prediction])


def generate_mock_weights(n_features: int = 5, seed: int = 42) -> np.ndarray:
    """Generate deterministic mock weights for demonstration."""
    rng = np.random.RandomState(seed)
    # Create weights for n_features + 1 (bias)
    weights = rng.randn(n_features + 1) * 0.1
    return weights.astype(np.float32)


# Predefined mock weights for different model versions
MOCK_MODELS: dict[str, dict[str, Any]] = {
    "v1": {
        "weights": np.array([0.3, 0.5, 0.2, 0.4, 0.1, 0.15], dtype=np.float32),
        "description": "Basic CNN-RNN model (6 parameters)",
        "parameters": 6,
        "val_loss": 0.0156,
    },
    "v2": {
        "weights": np.array([0.35, 0.45, 0.25, 0.38, 0.12, 0.18, 0.08], dtype=np.float32),
        "description": "Improved CNN-RNN (7 parameters)",
        "parameters": 7,
        "val_loss": 0.0123,
    },
    "v3": {
        "weights": np.array([0.32, 0.48, 0.22, 0.42, 0.11, 0.16, 0.09, 0.05], dtype=np.float32),
        "description": "Optimized CNN-RNN (8 parameters)",
        "parameters": 8,
        "val_loss": 0.0098,
    },
}


def get_available_models() -> list[dict[str, Any]]:
    """Return list of available demo model versions."""
    models = []
    for version, data in MOCK_MODELS.items():
        models.append(
            {
                "model_version": version,
                "parameters": data["parameters"],
                "weighted_val_loss": data["val_loss"],
                "description": data["description"],
            }
        )
    # Sort by version number
    models.sort(key=lambda x: x["model_version"])
    return models


def predict_demo(
    model_version: str,
    input_data: list[float],
) -> dict[str, Any]:
    """Run a demo prediction using mock weights.

    Args:
        model_version: The model version to use (e.g., "v1", "v2", "v3")
        input_data: List of input features (normalized values 0-1)

    Returns:
        Dictionary with prediction results
    """
    start_time = time.time()

    # Get weights for model version (fallback to v1)
    model_key = model_version if model_version in MOCK_MODELS else "v1"
    model_data = MOCK_MODELS[model_key]

    # Generate prediction
    weights = model_data["weights"]
    input_array = np.asarray(input_data, dtype=np.float32)

    # Scale input to reasonable prediction range
    prediction = float(np.dot(weights[: len(input_array)], input_array))
    if len(weights) > len(input_array):
        prediction += float(weights[len(input_array)])  # bias

    # Add some realistic noise
    noise = random.uniform(-0.02, 0.02)
    prediction = max(0.0, min(1.0, prediction + noise))

    latency_ms = int((time.time() - start_time) * 1000)

    # Generate explanation
    feature_contrib = [f"{w:.2f}×{v:.3f}" for w, v in zip(weights[: len(input_array)], input_data)]

    # Scale to PM2.5 range (0-300 µg/m³ for extreme events)
    scaled_prediction = min(1.0, prediction) * 300
    
    return {
        "predictions": [round(scaled_prediction, 1)],
        "model_version": model_key,
        "input": input_data,
        "output_shape": 1,
        "confidence": round(85 + abs(scaled_prediction - 150) / 3, 1),
        "latency_ms": latency_ms,
        "explanation": (
            f"Linear combination of inputs: {' + '.join(feature_contrib)}. "
            f"PM2.5 prediction: {scaled_prediction:.1f} µg/m³."
        ),
        "model_description": model_data["description"],
        "prediction_units": "µg/m³ (particles per cubic meter)",
    }


def predict_demo_advanced(
    model_version: str,
    input_data: list[float],
) -> dict[str, Any]:
    """Run an advanced mock prediction simulating CNN-RNN behavior.

    This creates more realistic predictions that simulate the behavior
    of a time-series model predicting air quality values.
    """
    start_time = time.time()

    # Get model config
    model_key = model_version if model_version in MOCK_MODELS else "v1"
    model_data = MOCK_MODELS[model_key]

    # Map normalized input to PM2.5 (0-1 -> 0-150 µg/m³ typical range)
    n_features = len(input_data)

    # Simulate model prediction with weighted average and some temporal smoothing
    weights = model_data["weights"][:n_features] if n_features <= len(model_data["weights"]) else model_data["weights"][: n_features - 1]
    
    # Simple weighted sum for prediction
    weighted_sum = sum(w * v for w, v in zip(weights, input_data))
    
    # Normalize and add bias
    bias = 0.15 if len(model_data["weights"]) > n_features else 0
    raw_prediction = weighted_sum + bias
    
    # Scale to PM2.5 range (0-300 µg/m³ for extreme events)
    scaled_prediction = raw_prediction * 300
    
    # Add seasonal/instrument noise
    noise = random.gauss(0, 10)
    prediction = max(0, min(300, scaled_prediction + noise))

    latency_ms = int((time.time() - start_time) * 1000)

    # Determine confidence based on input quality
    input_range = max(input_data) - min(input_data)
    confidence = 85 + input_range * 10  # Higher range = more confident

    return {
        "predictions": [round(prediction, 1)],
        "model_version": model_key,
        "input": input_data,
        "output_shape": 1,
        "confidence": round(confidence, 1),
        "latency_ms": latency_ms,
        "explanation": (
            f"Simulated CNN-RNN predicts PM2.5 = {prediction:.1f} µg/m³ "
            f"from {n_features} input features. Model: {model_data['description']}"
        ),
        "model_description": model_data["description"],
        "prediction_units": "µg/m³ (particles per cubic meter)",
    }


def generate_loss_epochs(
    model_version: str,
    epochs: int = 10,
) -> list[dict[str, Any]]:
    """Generate mock loss epoch data for a model version.
    
    This simulates the typical loss decay curve observed during training:
    - Rapid initial drop in first few epochs
    - Slower convergence in later epochs
    - Small plateaus and fluctuations
    
    Args:
        model_version: The model version (affects noise pattern)
        epochs: Number of epochs to generate
    
    Returns:
        List of dicts with 'epoch', 'train_loss', 'val_loss' keys
    """
    if model_version not in MOCK_MODELS:
        model_version = "v1"
    
    model_data = MOCK_MODELS[model_version]
    base_loss = model_data["val_loss"]
    
    # Use different seeds for each model version to get different curves
    rng = random.Random(hash(model_version) % (2**31))
    
    epoch_data = []
    for epoch in range(1, epochs + 1):
        # Simulate loss decay with diminishing returns
        progress = epoch / epochs
        
        # Base loss decays exponentially with some noise
        train_loss = base_loss + (0.05 - base_loss) * (1 - progress) + rng.gauss(0, 0.002)
        val_loss = train_loss + rng.gauss(0, 0.003)
        
        # Add slight noise variation based on model version differences
        train_loss = max(0.001, train_loss + rng.gauss(0, 0.001))
        val_loss = max(0.001, val_loss + rng.gauss(0, 0.0015))
        
        epoch_data.append({
            "epoch": epoch,
            "train_loss": round(train_loss, 6),
            "val_loss": round(val_loss, 6),
        })
    
    return epoch_data