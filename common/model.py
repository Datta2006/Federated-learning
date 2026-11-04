"""CNN-RNN model used by the central baselines and federated nodes.

Input:  (window_hours, 3) = last 3 hours of [pm2.5, temp, relative_humidity]
Output: next-hour scaled PM2.5
"""

from __future__ import annotations

import logging
import random
from typing import Any

import numpy as np
import tensorflow as tf


def set_seed(seed: int) -> None:
    """Set Python, NumPy, and TensorFlow seeds for reproducible runs."""
    random.seed(seed)
    np.random.seed(seed)
    tf.keras.utils.set_random_seed(seed)
    try:
        tf.config.experimental.enable_op_determinism()
    except (AttributeError, RuntimeError) as exc:
        logging.getLogger(__name__).warning("TF op determinism unavailable: %s", exc)


def build_model(
    window_hours: int,
    n_features: int,
    *,
    conv_filters: int = 64,
    kernel_size: int = 2,
    pool_size: int = 2,
    rnn_units: int = 64,
    dropout: float = 0.2,
    learning_rate: float = 0.001,
    seed: int = 42,
) -> tf.keras.Model:
    """Build Conv1D -> MaxPool -> Flatten -> reshape -> SimpleRNN -> Dense(1)."""
    set_seed(seed)
    inputs = tf.keras.Input(shape=(window_hours, n_features), name="window")
    x = tf.keras.layers.Conv1D(
        filters=conv_filters,
        kernel_size=kernel_size,
        padding="same",
        activation="relu",
        name="conv1d",
    )(inputs)
    x = tf.keras.layers.MaxPooling1D(pool_size=pool_size, name="maxpool")(x)
    x = tf.keras.layers.Flatten(name="flatten")(x)
    x = tf.keras.layers.Reshape((-1, conv_filters), name="reshape_for_rnn")(x)
    x = tf.keras.layers.SimpleRNN(
        rnn_units, dropout=dropout, name="simple_rnn"
    )(x)
    outputs = tf.keras.layers.Dense(1, name="pm25_next_hour")(x)

    model = tf.keras.Model(inputs=inputs, outputs=outputs, name="cnn_rnn_pm25")
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="mse",
        metrics=["mae"],
    )
    return model


def make_callbacks(patience: int, verbose: int = 0) -> list[tf.keras.callbacks.Callback]:
    """Early stopping; restore the best validation weights."""
    return [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=patience,
            restore_best_weights=True,
            verbose=verbose,
        )
    ]


def flatten_weights(model: tf.keras.Model) -> np.ndarray:
    """Flatten every model weight into one contiguous float32 vector."""
    arrays = [np.asarray(weight, dtype=np.float32).ravel() for weight in model.get_weights()]
    if not arrays:
        return np.empty(0, dtype=np.float32)
    return np.concatenate(arrays).astype(np.float32, copy=False)


def unflatten_weights(model: tf.keras.Model, flat_weights: np.ndarray) -> None:
    """Restore a flat float32 vector into a model with matching weight shapes."""
    flat = np.asarray(flat_weights, dtype=np.float32).reshape(-1)
    restored: list[np.ndarray] = []
    offset = 0
    for weight in model.get_weights():
        size = int(np.prod(weight.shape))
        if offset + size > flat.size:
            raise ValueError(
                f"flat weight vector is too short: need at least {offset + size}, "
                f"got {flat.size}"
            )
        restored.append(flat[offset : offset + size].reshape(weight.shape))
        offset += size
    if offset != flat.size:
        raise ValueError(
            f"flat weight vector has {flat.size - offset} unexpected extra value(s)"
        )
    model.set_weights(restored)


def model_summary(model: tf.keras.Model) -> dict[str, Any]:
    """Return a small JSON-friendly summary used in logs and metadata."""
    return {
        "name": model.name,
        "parameters": int(model.count_params()),
        "input_shape": list(model.input_shape),
        "output_shape": list(model.output_shape),
    }
