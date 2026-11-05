"""Unit tests for the pure Stage 4 federated rules."""

from __future__ import annotations

import numpy as np
import pytest

from common.chunking import sha256_hex
from common.federated import (
    UpdateValidationError,
    fedavg,
    is_newer_version,
    model_version_for_round,
    validate_update,
    validate_update_metadata,
    weighted_validation_loss,
)
from common.weight_transfer import (
    build_transfer_metadata,
    encode_weights,
    make_dummy_weights,
)

TRAINING_NODES = {"node1", "node2", "node3", "node4"}
INFERENCE_NODES = {"node5"}


def _update_metadata(weights: np.ndarray, *, node_id: str = "node1"):
    metadata = build_transfer_metadata(
        weights,
        node_id=node_id,
        model_version="v0001",
        model_config={},
        kind="dummy",
        round_number=1,
        chunk_size=2048,
    )
    metadata.update({"n_samples": 100, "n_val": 20, "val_loss": 0.5})
    return metadata


def test_fedavg_matches_a_hand_computed_unequal_weight_example():
    first = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    second = np.array([10.0, 20.0, 30.0], dtype=np.float32)

    result = fedavg([first, second], [1, 3])

    # (1*[1,2,3] + 3*[10,20,30]) / 4 = [7.75, 15.5, 23.25]
    np.testing.assert_allclose(result, np.array([7.75, 15.5, 23.25]), rtol=0, atol=1e-6)
    assert result.dtype == np.float32


def test_fedavg_rejects_mismatched_shapes_and_empty_samples():
    with pytest.raises(ValueError, match="same shape"):
        fedavg([np.zeros(2), np.zeros(3)], [1, 1])
    with pytest.raises(ValueError, match="positive"):
        fedavg([np.zeros(2)], [0])


def test_weighted_validation_loss_uses_node_sample_counts():
    assert weighted_validation_loss([(1.0, 100), (3.0, 300)]) == pytest.approx(2.5)
    with pytest.raises(ValueError, match="at least one"):
        weighted_validation_loss([])


def test_model_version_names_are_monotonic():
    assert model_version_for_round(1) == "v0001"
    assert model_version_for_round(12) == "v0012"
    assert is_newer_version("v0002", "v0001") is True
    assert is_newer_version("v0001", "v0002") is False


def test_validate_update_accepts_a_complete_normal_update():
    weights = make_dummy_weights(16, seed=3)
    metadata = _update_metadata(weights)
    payload = encode_weights(weights)

    validated = validate_update(
        metadata,
        payload,
        expected_round=1,
        expected_model_version="v0001",
        training_nodes=TRAINING_NODES,
        inference_only_nodes=INFERENCE_NODES,
    )

    np.testing.assert_array_equal(validated, weights)


def test_validate_update_rejects_nan_weights():
    payload = np.array([np.nan, 1.0], dtype=np.float32).tobytes()
    metadata = _update_metadata(make_dummy_weights(2))
    metadata.update(
        {
            "sha256": sha256_hex(payload),
            "size": len(payload),
            "count": 2,
            "chunks": 1,
            "chunk_size": len(payload),
        }
    )

    with pytest.raises(UpdateValidationError, match="NaN"):
        validate_update(metadata, payload)


def test_validate_update_rejects_a_whole_payload_checksum_mismatch():
    weights = make_dummy_weights(16, seed=4)
    metadata = _update_metadata(weights)
    payload = bytearray(encode_weights(weights))
    payload[0] ^= 0xFF

    with pytest.raises(UpdateValidationError, match="checksum"):
        validate_update(metadata, bytes(payload))


def test_validate_update_rejects_the_wrong_round():
    weights = make_dummy_weights(16, seed=5)
    metadata = _update_metadata(weights)

    with pytest.raises(UpdateValidationError, match="round"):
        validate_update(metadata, encode_weights(weights), expected_round=2)


def test_validate_update_rejects_an_inference_only_sender():
    weights = make_dummy_weights(16, seed=6)
    metadata = _update_metadata(weights, node_id="node5")

    with pytest.raises(UpdateValidationError, match="inference-only"):
        validate_update(
            metadata,
            encode_weights(weights),
            training_nodes=TRAINING_NODES,
            inference_only_nodes=INFERENCE_NODES,
        )


def test_validate_update_rejects_an_abnormal_weight_norm():
    weights = np.full(16, 1e6, dtype=np.float32)
    metadata = _update_metadata(weights)

    with pytest.raises(UpdateValidationError, match="abnormal"):
        validate_update(
            metadata,
            encode_weights(weights),
            reference_weights=np.ones(16, dtype=np.float32),
        )


def test_validate_update_metadata_requires_validation_fields():
    weights = make_dummy_weights(8)
    metadata = _update_metadata(weights)
    metadata.pop("n_val")

    with pytest.raises(UpdateValidationError, match="n_val"):
        validate_update_metadata(metadata)
