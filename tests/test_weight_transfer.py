"""Unit tests for the Stage 3 chunked-weight transfer seam.

The tests use a dummy float32 array first. One opt-in test builds the real
improved 24 h Keras model and checks that a round trip preserves both the flat
weight vector and the model's predictions.
"""

from __future__ import annotations

import base64

import numpy as np
import pytest

from common.chunking import sha256_hex
from common.config import (
    inference_only_node_ids,
    load_config,
    training_node_ids,
)
from common.weight_transfer import (
    TransferError,
    WeightReceiver,
    build_ack_message,
    build_chunk_message,
    build_transfer_metadata,
    decode_weights,
    encode_weights,
    global_announce_topic,
    global_chunk_filter,
    global_chunk_topic,
    make_dummy_weights,
    prediction_digest,
    round_ack_topic,
    round_update_chunk_filter,
    round_update_chunk_topic,
    round_update_meta_filter,
    round_update_meta_topic,
    split_weight_payload,
    validate_header,
    validate_transfer_metadata,
)


def _dummy_transfer(*, chunk_size: int = 8192, sha256: str | None = None):
    weights = make_dummy_weights(count=5000, seed=7)
    payload = encode_weights(weights)
    metadata = build_transfer_metadata(
        weights,
        node_id="node1",
        model_version="dummy-v1",
        model_config={},
        kind="dummy",
        chunk_size=chunk_size,
        prediction_sha256=None,
    )
    if sha256 is not None:
        metadata["sha256"] = sha256
    chunks = split_weight_payload(payload, chunk_size)
    return weights, metadata, chunks


def test_encode_decode_round_trip_preserves_float32_values():
    weights = make_dummy_weights(count=37, seed=3)

    restored = decode_weights(encode_weights(weights), "float32", weights.size)

    np.testing.assert_array_equal(restored, weights)
    assert restored.dtype == np.float32


def test_metadata_has_required_header_and_three_chunks_for_9025_weights():
    weights = make_dummy_weights(count=9025, seed=42)

    metadata = build_transfer_metadata(
        weights,
        node_id="node1",
        model_version="improved_w24",
        model_config={"window_hours": 24, "n_features": 5, "pool_size": 1},
        kind="model",
    )

    assert metadata["schema_version"] == 1
    assert metadata["node_id"] == "node1"
    assert metadata["ts"].endswith("Z")
    assert metadata["sha256"] == sha256_hex(encode_weights(weights))
    assert metadata["size"] == 36100
    assert metadata["chunks"] == 3
    assert metadata["chunk_size"] == 16384
    assert metadata["count"] == 9025
    validate_transfer_metadata(metadata)


def test_receiver_accepts_out_of_order_chunks_and_reassembles():
    weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)

    for index in [2, 0, 1]:
        receiver.accept_chunk(index, chunks[index])

    assert receiver.complete is True
    payload = receiver.finalize()
    np.testing.assert_array_equal(
        decode_weights(payload, metadata["dtype"], metadata["count"]), weights
    )


def test_receiver_tolerates_an_identical_qos1_duplicate():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)
    receiver.accept_chunk(0, chunks[0])

    assert receiver.accept_chunk(0, chunks[0]) == "duplicate"
    for index in range(1, len(chunks)):
        receiver.accept_chunk(index, chunks[index])

    assert receiver.finalize()


def test_receiver_rejects_a_conflicting_duplicate():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)
    receiver.accept_chunk(0, chunks[0])

    with pytest.raises(TransferError, match="conflicting duplicate"):
        receiver.accept_chunk(0, chunks[0][:-1] + b"x")

    assert receiver.fatal_error is not None


def test_receiver_rejects_a_chunk_with_bad_sha256():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)
    bad = bytearray(chunks[0])
    bad[0] ^= 0xFF

    with pytest.raises(TransferError, match="chunk checksum"):
        receiver.accept_chunk(
            0,
            bytes(bad),
            chunk_sha256=sha256_hex(chunks[0]),
        )

    assert receiver.fatal_error is not None


def test_receiver_rejects_a_missing_chunk():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)
    receiver.accept_chunk(0, chunks[0])
    receiver.accept_chunk(2, chunks[2])

    assert receiver.missing_indices == [1]
    with pytest.raises(TransferError, match="missing"):
        receiver.finalize()


def test_receiver_rejects_a_total_checksum_mismatch():
    _weights, metadata, chunks = _dummy_transfer(
        sha256=sha256_hex(b"different payload")
    )
    receiver = WeightReceiver(metadata)
    for index, chunk in enumerate(chunks):
        receiver.accept_chunk(index, chunk)

    with pytest.raises(TransferError, match="checksum"):
        receiver.finalize()


def test_receiver_rejects_a_topic_index_that_disagrees_with_the_message():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)

    with pytest.raises(TransferError, match="topic index"):
        receiver.accept_chunk(0, chunks[0], topic_index=1)


def test_receiver_rejects_an_out_of_range_chunk_index():
    _weights, metadata, chunks = _dummy_transfer()
    receiver = WeightReceiver(metadata)

    with pytest.raises(TransferError, match="out of range"):
        receiver.accept_chunk(99, chunks[0])


def test_metadata_validation_rejects_a_wrong_chunk_count():
    _weights, metadata, _chunks = _dummy_transfer()
    metadata["chunks"] = 999

    with pytest.raises(ValueError, match="chunks"):
        validate_transfer_metadata(metadata)


def test_header_validation_rejects_a_non_iso_timestamp():
    _weights, metadata, _chunks = _dummy_transfer()
    metadata["ts"] = "garbageZ"

    with pytest.raises(TransferError, match="ts"):
        validate_header(metadata)


def test_live_topology_is_four_training_nodes_plus_one_inference_node():
    config = load_config()

    assert training_node_ids(config) == {"node1", "node2", "node3", "node4"}
    assert inference_only_node_ids(config) == {"node5"}
    assert not training_node_ids(config) & inference_only_node_ids(config)


def test_sender_refuses_an_inference_only_weight_upload():
    from node.weight_sender import run

    with pytest.raises(ValueError, match="inference-only"):
        run(node_id="node5", host="127.0.0.1", port=1)


def test_topic_builders_and_parsers_use_the_stage3_contract():
    assert global_announce_topic("aq") == "aq/fl/global/announce"
    assert global_chunk_topic("aq", 2) == "aq/fl/global/chunk/2"
    assert global_chunk_filter("aq") == "aq/fl/global/chunk/+"
    assert round_update_meta_topic("aq", 3, "node1") == (
        "aq/fl/round/3/update/node1/meta"
    )
    assert round_update_chunk_topic("aq", 3, "node1", 0) == (
        "aq/fl/round/3/update/node1/chunk/0"
    )
    assert round_update_meta_filter("aq") == "aq/fl/round/+/update/+/meta"
    assert round_update_chunk_filter("aq") == "aq/fl/round/+/update/+/chunk/+"
    assert round_ack_topic("aq", 3, "node1") == "aq/fl/round/3/ack/node1"


def test_chunk_message_is_json_safe_and_contains_sequence_and_sha():
    _weights, metadata, chunks = _dummy_transfer()
    message = build_chunk_message(metadata, 1, chunks[1])

    assert message["schema_version"] == 1
    assert message["node_id"] == "node1"
    assert message["ts"].endswith("Z")
    assert message["index"] == 1
    assert message["chunks"] == len(chunks)
    assert message["chunk_sha256"] == sha256_hex(chunks[1])
    assert base64.b64decode(message["data"]) == chunks[1]


def test_ack_message_reports_acceptance_without_raw_readings():
    _weights, metadata, _chunks = _dummy_transfer()
    ack = build_ack_message(
        metadata,
        status="accepted",
        chunks_received=len(_chunks),
        predictions_match=True,
    )

    assert ack["schema_version"] == 1
    assert ack["node_id"] == "flserver"
    assert ack["ts"].endswith("Z")
    assert ack["status"] == "accepted"
    assert ack["chunks_received"] == len(_chunks)
    assert "pm25" not in ack
    assert "readings" not in ack


def test_real_improved_24h_weights_round_trip_and_predictions_are_unchanged():
    tf = pytest.importorskip("tensorflow")  # noqa: F841
    from common.model import build_model, flatten_weights, unflatten_weights

    model = build_model(
        window_hours=24,
        n_features=5,
        pool_size=1,
        seed=42,
    )
    weights = flatten_weights(model)
    probe = np.random.default_rng(42).uniform(0.0, 1.0, size=(4, 24, 5))
    probe = probe.astype(np.float32)
    before = model.predict(probe, verbose=0)

    metadata = build_transfer_metadata(
        weights,
        node_id="node1",
        model_version="improved_w24_seed42",
        model_config={
            "window_hours": 24,
            "n_features": 5,
            "conv_filters": 64,
            "kernel_size": 2,
            "pool_size": 1,
            "rnn_units": 64,
            "dropout": 0.2,
            "learning_rate": 0.001,
            "seed": 42,
        },
        kind="model",
        prediction_sha256=prediction_digest(before),
    )
    payload = encode_weights(weights)
    chunks = split_weight_payload(payload, metadata["chunk_size"])
    receiver = WeightReceiver(metadata)
    for index in [2, 0, 1]:
        receiver.accept_chunk(index, chunks[index])
    restored_weights = decode_weights(
        receiver.finalize(), metadata["dtype"], metadata["count"]
    )

    np.testing.assert_array_equal(restored_weights, weights)
    restored = build_model(window_hours=24, n_features=5, pool_size=1, seed=42)
    unflatten_weights(restored, restored_weights)
    after = restored.predict(probe, verbose=0)

    np.testing.assert_array_equal(after, before)
    assert prediction_digest(after) == metadata["prediction_sha256"]
