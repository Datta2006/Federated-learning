"""Chunk large payloads and reassemble them with sequence + SHA-256 checks.

The same helper is used for federated model weights on the wire.  A chunk is
identified by its zero-based sequence number; the final reassembly checks that
all chunks arrived exactly once and that the SHA-256 digest matches.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

DEFAULT_CHUNK_SIZE = 16 * 1024


class ChunkError(ValueError):
    """Raised when a chunk sequence or checksum is invalid."""


def sha256_hex(payload: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *payload*."""
    return hashlib.sha256(payload).hexdigest()


def split_payload(payload: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[bytes]:
    """Split *payload* into fixed-size chunks (the final chunk may be shorter)."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    return [bytes(payload[i : i + chunk_size]) for i in range(0, len(payload), chunk_size)]


class ChunkAssembler:
    """Collect out-of-order chunks and verify the completed payload."""

    def __init__(self, total_chunks: int, expected_sha256: str | None) -> None:
        if total_chunks <= 0:
            raise ValueError("total_chunks must be positive")
        if expected_sha256 is not None:
            expected_sha256 = expected_sha256.lower()
            if len(expected_sha256) != 64:
                raise ValueError("expected_sha256 must be a 64-character hex digest")
        self.total_chunks = total_chunks
        self.expected_sha256 = expected_sha256
        self._chunks: dict[int, bytes] = {}

    def add(self, index: int, chunk: bytes) -> None:
        """Add one chunk.  Duplicate or out-of-range indexes are rejected."""
        if not isinstance(index, int):
            raise ChunkError(f"chunk index must be int, got {type(index).__name__}")
        if index < 0 or index >= self.total_chunks:
            raise ChunkError(
                f"chunk index {index} out of range for {self.total_chunks} chunks"
            )
        if index in self._chunks:
            raise ChunkError(f"duplicate chunk index {index}")
        if not isinstance(chunk, (bytes, bytearray)):
            raise ChunkError("chunk payload must be bytes")
        self._chunks[index] = bytes(chunk)

    @property
    def missing_indices(self) -> list[int]:
        """Return the zero-based sequence numbers that have not arrived."""
        return [i for i in range(self.total_chunks) if i not in self._chunks]

    @property
    def complete(self) -> bool:
        """True when every sequence number has been received exactly once."""
        return len(self._chunks) == self.total_chunks

    def reassemble(self) -> bytes:
        """Join chunks in sequence order and verify the SHA-256 digest."""
        missing = self.missing_indices
        if missing:
            raise ChunkError(f"missing chunks: {missing}")
        payload = b"".join(self._chunks[i] for i in range(self.total_chunks))
        if self.expected_sha256 is not None:
            actual = sha256_hex(payload)
            if actual != self.expected_sha256:
                raise ChunkError(
                    f"checksum mismatch: expected {self.expected_sha256}, got {actual}"
                )
        return payload


def reassemble(chunks: Iterable[bytes], expected_sha256: str | None = None) -> bytes:
    """Convenience helper for an already-ordered chunk list."""
    ordered = list(chunks)
    assembler = ChunkAssembler(len(ordered), expected_sha256)
    for index, chunk in enumerate(ordered):
        assembler.add(index, chunk)
    return assembler.reassemble()
