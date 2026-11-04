"""Unit tests for chunking, sequencing, and SHA-256 verification."""

import hashlib

import pytest

from common.chunking import ChunkAssembler, ChunkError, sha256_hex, split_payload


def test_split_payload_uses_fixed_size_and_preserves_bytes():
    payload = b"abcdefghij"

    chunks = split_payload(payload, chunk_size=4)

    assert chunks == [b"abcd", b"efgh", b"ij"]


def test_sha256_hex_matches_hashlib():
    payload = b"federated-pm25"

    assert sha256_hex(payload) == hashlib.sha256(payload).hexdigest()


def test_assembler_reassembles_out_of_order_chunks():
    payload = b"the quick brown fox"
    chunks = split_payload(payload, chunk_size=5)
    assembler = ChunkAssembler(
        total_chunks=len(chunks), expected_sha256=sha256_hex(payload)
    )

    for index in [3, 0, 2, 1]:
        assembler.add(index, chunks[index])

    assert assembler.complete is True
    assert assembler.reassemble() == payload


def test_assembler_rejects_bad_checksum():
    payload = b"weights"
    assembler = ChunkAssembler(
        total_chunks=1, expected_sha256=sha256_hex(b"different")
    )
    assembler.add(0, payload)

    with pytest.raises(ChunkError, match="checksum"):
        assembler.reassemble()


def test_assembler_rejects_duplicate_chunk():
    assembler = ChunkAssembler(total_chunks=2, expected_sha256=None)
    assembler.add(0, b"a")

    with pytest.raises(ChunkError, match="duplicate"):
        assembler.add(0, b"a")


def test_assembler_rejects_out_of_range_chunk():
    assembler = ChunkAssembler(total_chunks=2, expected_sha256=None)

    with pytest.raises(ChunkError, match="out of range"):
        assembler.add(2, b"x")


def test_assembler_reports_missing_chunks():
    assembler = ChunkAssembler(total_chunks=3, expected_sha256=None)
    assembler.add(0, b"a")
    assembler.add(2, b"c")

    assert assembler.missing_indices == [1]
    with pytest.raises(ChunkError, match="missing"):
        assembler.reassemble()
