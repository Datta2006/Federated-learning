"""Pure federated-learning rules: weighted FedAvg, validation, and versions.

This module has no MQTT, TensorFlow, or filesystem dependency.  The coordinator
and node adapters call these functions so the round rules can be tested at a
small seam.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

import numpy as np

from common.chunking import sha256_hex
from common.weight_transfer import (
    TransferError,
    decode_weights,
    validate_transfer_metadata,
)

DEFAULT_MAX_ABS_WEIGHT = 1e4
DEFAULT_MAX_WEIGHT_NORM = 1e6
DEFAULT_NORM_MULTIPLIER = 10.0
_VERSION_PATTERN = re.compile(r"^v([0-9]{4,})$")


class UpdateValidationError(ValueError):
    """Raised when a node update violates the Stage 4 round contract."""


def model_version_for_round(round_number: int) -> str:
    """Return the registry version name for a round, e.g. ``v0007``."""
    if isinstance(round_number, bool) or not isinstance(round_number, int):
        raise TypeError("round_number must be an integer")
    if round_number < 0:
        raise ValueError("round_number must be non-negative")
    return f"v{round_number:04d}"


def model_version_number(version: str) -> int | None:
    """Parse ``v0007`` into 7; return None for a non-version token."""
    if not isinstance(version, str):
        return None
    match = _VERSION_PATTERN.fullmatch(version)
    return int(match.group(1)) if match else None


def is_newer_version(candidate: str, current: str | None) -> bool:
    """True when *candidate* is a strictly newer registry version."""
    if current is None:
        return True
    candidate_number = model_version_number(candidate)
    current_number = model_version_number(current)
    if candidate_number is None or current_number is None:
        return candidate > current
    return candidate_number > current_number


def _as_weights(value: Any, name: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != 1:
        raise ValueError(f"{name} must be a 1-D array")
    if array.size == 0:
        raise ValueError(f"{name} must not be empty")
    if not np.isfinite(array).all():
        raise ValueError(f"{name} contains NaN or Infinity")
    return array


def _as_sample_counts(value: Any, expected: int) -> np.ndarray:
    if len(value) != expected:
        raise ValueError("weight vectors and n_samples must have the same length")
    counts = np.asarray(value)
    if counts.ndim != 1:
        raise ValueError("n_samples must be a 1-D sequence")
    if not np.issubdtype(counts.dtype, np.integer):
        raise ValueError("n_samples must contain integers")
    if np.any(counts <= 0):
        raise ValueError("n_samples must contain positive integers")
    return counts.astype(np.int64)


def fedavg(
    weight_vectors: Sequence[np.ndarray], n_samples: Sequence[int]
) -> np.ndarray:
    """Weighted average of flat float32 vectors, weighted by sample count."""
    vectors = [_as_weights(vector, "weight vector") for vector in weight_vectors]
    if not vectors:
        raise ValueError("at least one weight vector is required")
    shape = vectors[0].shape
    if any(vector.shape != shape for vector in vectors[1:]):
        raise ValueError("all weight vectors must have the same shape")
    counts = _as_sample_counts(n_samples, len(vectors))
    total = int(counts.sum())
    if total <= 0:
        raise ValueError("n_samples must sum to a positive value")
    stacked = np.stack(vectors, axis=0).astype(np.float64, copy=False)
    averaged = np.average(stacked, axis=0, weights=counts)
    return averaged.astype(np.float32)


def weighted_average(values: Sequence[float], weights: Sequence[int]) -> float:
    """Weighted average of scalar values; used for global validation loss."""
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    if not values:
        raise ValueError("at least one value is required")
    counts = _as_sample_counts(weights, len(values))
    numbers = np.asarray(values, dtype=np.float64)
    if not np.isfinite(numbers).all():
        raise ValueError("values contain NaN or Infinity")
    total = int(counts.sum())
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    return float(np.average(numbers, weights=counts))


def weighted_validation_loss(
    reported: Sequence[tuple[float, int]],
) -> float:
    """Compute ``sum(val_loss * n_val) / sum(n_val)`` for node reports."""
    if not reported:
        raise ValueError("at least one validation report is required")
    losses = [loss for loss, _count in reported]
    counts = [count for _loss, count in reported]
    return weighted_average(losses, counts)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise UpdateValidationError(f"{name} must be a positive integer")
    return value


def _finite_non_negative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise UpdateValidationError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise UpdateValidationError(f"{name} must be finite and non-negative")
    return number


def validate_update_metadata(
    metadata: dict[str, Any],
    *,
    expected_round: int | None = None,
    expected_model_version: str | None = None,
    training_nodes: set[str] | None = None,
    inference_only_nodes: set[str] | None = None,
) -> None:
    """Validate the metadata half of a node update before chunks arrive."""
    try:
        validate_transfer_metadata(metadata)
    except (TypeError, ValueError, TransferError) as exc:
        raise UpdateValidationError(str(exc)) from exc
    if metadata.get("message_type") != "update_meta":
        raise UpdateValidationError("round update has the wrong message_type")

    node_id = metadata.get("node_id")
    if inference_only_nodes and node_id in inference_only_nodes:
        raise UpdateValidationError(
            "node is inference-only and must not upload weights"
        )
    if training_nodes is not None and node_id not in training_nodes:
        raise UpdateValidationError("node is not a training node")

    if expected_round is not None and metadata.get("round") != expected_round:
        raise UpdateValidationError(
            f"round mismatch: expected {expected_round}, got {metadata.get('round')}"
        )
    if (
        expected_model_version is not None
        and metadata.get("model_version") != expected_model_version
    ):
        raise UpdateValidationError(
            f"model_version mismatch: expected {expected_model_version}, "
            f"got {metadata.get('model_version')}"
        )

    _positive_int(metadata.get("n_samples"), "n_samples")
    _positive_int(metadata.get("n_val"), "n_val")
    _finite_non_negative(metadata.get("val_loss"), "val_loss")


def _validate_norm(
    weights: np.ndarray,
    *,
    reference_weights: np.ndarray | None,
    max_abs_weight: float,
    max_weight_norm: float,
    norm_multiplier: float,
) -> None:
    maximum = float(np.max(np.abs(weights)))
    if maximum > max_abs_weight:
        raise UpdateValidationError(
            f"abnormal weight magnitude: max |w|={maximum:.6g} > {max_abs_weight:.6g}"
        )
    norm = float(np.linalg.norm(weights.astype(np.float64)))
    if not math.isfinite(norm) or norm > max_weight_norm:
        raise UpdateValidationError(
            f"abnormal weight norm: {norm:.6g} > {max_weight_norm:.6g}"
        )
    if reference_weights is not None:
        reference = np.asarray(reference_weights, dtype=np.float64).reshape(-1)
        reference_norm = float(np.linalg.norm(reference))
        limit = max(reference_norm * norm_multiplier, reference_norm + 1.0)
        if norm > limit:
            raise UpdateValidationError(
                f"abnormal weight norm: {norm:.6g} > {limit:.6g} "
                f"(reference norm {reference_norm:.6g})"
            )


def validate_update(
    metadata: dict[str, Any],
    payload: bytes,
    *,
    expected_round: int | None = None,
    expected_model_version: str | None = None,
    training_nodes: set[str] | None = None,
    inference_only_nodes: set[str] | None = None,
    reference_weights: np.ndarray | None = None,
    max_abs_weight: float = DEFAULT_MAX_ABS_WEIGHT,
    max_weight_norm: float = DEFAULT_MAX_WEIGHT_NORM,
    norm_multiplier: float = DEFAULT_NORM_MULTIPLIER,
) -> np.ndarray:
    """Validate metadata plus a complete payload and return float32 weights."""
    validate_update_metadata(
        metadata,
        expected_round=expected_round,
        expected_model_version=expected_model_version,
        training_nodes=training_nodes,
        inference_only_nodes=inference_only_nodes,
    )
    actual_sha = sha256_hex(payload)
    if actual_sha != metadata["sha256"]:
        raise UpdateValidationError(
            f"checksum mismatch: metadata says {metadata['sha256']}, got {actual_sha}"
        )
    try:
        weights = decode_weights(payload, metadata["dtype"], metadata["count"])
    except (TypeError, ValueError, TransferError) as exc:
        raise UpdateValidationError(str(exc)) from exc
    if not np.isfinite(weights).all():
        raise UpdateValidationError("weights contain NaN or Infinity")
    if reference_weights is not None:
        reference = np.asarray(reference_weights).reshape(-1)
        if weights.size != reference.size:
            raise UpdateValidationError(
                f"weight count mismatch: update has {weights.size}, "
                f"global model has {reference.size}"
            )
    _validate_norm(
        weights,
        reference_weights=reference_weights,
        max_abs_weight=max_abs_weight,
        max_weight_norm=max_weight_norm,
        norm_multiplier=norm_multiplier,
    )
    return weights
