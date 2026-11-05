"""Stage 3 chunked weight transfer: topics, metadata, chunks, and validation.

The module is deliberately transport-agnostic.  It turns a float32 weight vector
into a small JSON metadata object plus 16 KiB base64 chunks, and it reassembles
those chunks with sequence checks, per-chunk SHA-256, and a whole-payload
SHA-256.  The MQTT adapters live in :mod:`node.weight_sender` and
:mod:`server.weight_receiver`; tests exercise this seam directly.

Privacy rule: this module carries model weights, checksums, and prediction
digests only.  It has no path for raw PM2.5/temperature/humidity readings.
"""

from __future__ import annotations

import base64
import binascii
import math
import re
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from common.chunking import ChunkAssembler, ChunkError, sha256_hex, split_payload
from common.mqtt_utils import SCHEMA_VERSION, make_message

DEFAULT_CHUNK_SIZE = 16 * 1024
SUPPORTED_DTYPES = {"float32"}
_SUPPORTED_DTYPE_SIZES = {"float32": 4}
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]+$")
_TRANSFER_MESSAGE_TYPES = {"announce", "update_meta"}


class TransferError(ValueError):
    """Raised when transfer metadata, a chunk, or a checksum is invalid."""


def _require_safe_token(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")
    if not _SAFE_TOKEN.fullmatch(value):
        raise ValueError(
            f"{name} must contain only letters, digits, '_', '.', ':', or '-'; "
            f"got {value!r}"
        )
    return value


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX_SHA256.fullmatch(value.lower()):
        raise ValueError(f"{name} must be a 64-character hex SHA-256 digest")
    return value.lower()


def _require_positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def validate_header(
    message: dict[str, Any], *, expected_node_id: str | None = None
) -> None:
    """Validate the schema/node/timestamp header every Stage 3 JSON must carry."""
    if not isinstance(message, dict):
        raise TransferError("MQTT payload must be a JSON object")
    if message.get("schema_version") != SCHEMA_VERSION:
        raise TransferError(
            f"schema_version must be {SCHEMA_VERSION}; "
            f"got {message.get('schema_version')!r}"
        )
    node_id = message.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise TransferError("node_id must be a non-empty string")
    _require_safe_token(node_id, "node_id")
    if expected_node_id is not None and node_id != expected_node_id:
        raise TransferError(
            f"node_id mismatch: expected {expected_node_id!r}, got {node_id!r}"
        )
    ts = message.get("ts")
    if not isinstance(ts, str) or not ts.endswith("Z") or "T" not in ts:
        raise TransferError("ts must be a UTC ISO-8601 string ending in Z")
    try:
        parsed_ts = datetime.fromisoformat(ts[:-1] + "+00:00")
    except ValueError as exc:
        raise TransferError("ts must be a valid UTC ISO-8601 timestamp") from exc
    if parsed_ts.utcoffset() != timedelta(0):
        raise TransferError("ts must be a valid UTC ISO-8601 timestamp")


def chunk_count(size: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> int:
    """Number of chunks needed for *size* bytes."""
    size = _require_positive_int(size, "size")
    chunk_size = _require_positive_int(chunk_size, "chunk_size")
    return math.ceil(size / chunk_size)


def _expected_chunk_size(metadata: dict[str, Any], index: int) -> int:
    """Raw byte length of chunk *index*: full chunks plus a shorter last one."""
    if index < metadata["chunks"] - 1:
        return metadata["chunk_size"]
    return metadata["size"] - index * metadata["chunk_size"]


def make_dummy_weights(count: int = 9025, seed: int = 42) -> np.ndarray:
    """Deterministic float32 array used to test plumbing before real weights."""
    count = _require_positive_int(count, "count")
    offsets = np.arange(count, dtype=np.float32)
    # Include the seed without random state so the demo is repeatable.
    return ((offsets + float(seed)) / 1000.0).astype(np.float32)


def encode_weights(weights: np.ndarray) -> bytes:
    """Flatten a weight array to contiguous little-endian float32 bytes."""
    array = np.asarray(weights)
    if array.ndim != 1:
        raise ValueError("weights must be a 1-D array")
    if array.size == 0:
        raise ValueError("weights must not be empty")
    if array.dtype != np.float32:
        array = array.astype(np.float32)
    if not np.isfinite(array).all():
        raise ValueError("weights contain NaN or Infinity")
    if not array.flags.c_contiguous:
        array = np.ascontiguousarray(array)
    return array.tobytes(order="C")


def decode_weights(payload: bytes, dtype: str, count: int) -> np.ndarray:
    """Rebuild a float32 array and reject a size or dtype mismatch."""
    if dtype not in SUPPORTED_DTYPES:
        raise TransferError(f"unsupported weight dtype {dtype!r}")
    count = _require_positive_int(count, "count")
    array = np.frombuffer(payload, dtype=np.dtype(dtype))
    if array.size != count:
        raise TransferError(
            f"weight count mismatch: metadata says {count}, payload has {array.size}"
        )
    if not np.isfinite(array).all():
        raise TransferError("weights contain NaN or Infinity")
    return array.astype(np.float32, copy=True)


def build_transfer_metadata(
    weights: np.ndarray,
    *,
    node_id: str,
    model_version: str,
    model_config: dict[str, Any],
    kind: str = "model",
    round_number: int | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    probe_seed: int = 42,
    prediction_sha256: str | None = None,
    prediction_sample: list[float] | None = None,
) -> dict[str, Any]:
    """Build announce/update metadata for one weight vector.

    ``kind="dummy"`` is for plumbing tests only.  ``kind="model"`` requires a
    model config that is sufficient to rebuild the same Keras architecture.
    """
    _require_safe_token(node_id, "node_id")
    _require_safe_token(model_version, "model_version")
    chunk_size = _require_positive_int(chunk_size, "chunk_size")
    if kind not in {"model", "dummy"}:
        raise ValueError("kind must be 'model' or 'dummy'")
    if kind == "model" and not model_config:
        raise ValueError("model_config is required for kind='model'")
    if round_number is not None:
        round_number = _require_positive_int(round_number, "round_number")

    payload = encode_weights(weights)
    message_type = "update_meta" if round_number is not None else "announce"
    fields: dict[str, Any] = {
        "message_type": message_type,
        "model_version": model_version,
        "sha256": sha256_hex(payload),
        "size": len(payload),
        "chunks": chunk_count(len(payload), chunk_size),
        "chunk_size": chunk_size,
        "dtype": "float32",
        "count": int(np.asarray(weights).size),
        "kind": kind,
        "model": dict(model_config),
        "probe_seed": int(probe_seed),
        "prediction_sha256": (
            _require_sha256(prediction_sha256, "prediction_sha256")
            if prediction_sha256 is not None
            else None
        ),
        "prediction_sample": (
            [float(value) for value in prediction_sample]
            if prediction_sample is not None
            else None
        ),
    }
    if round_number is not None:
        fields["round"] = round_number
    metadata = make_message(node_id, **fields)
    validate_transfer_metadata(metadata)
    return metadata


def validate_transfer_metadata(metadata: dict[str, Any]) -> None:
    """Reject incomplete or internally inconsistent announce/update metadata."""
    validate_header(metadata)
    message_type = metadata.get("message_type")
    if message_type not in _TRANSFER_MESSAGE_TYPES:
        raise ValueError(f"not transfer metadata: message_type={message_type!r}")
    _require_safe_token(metadata.get("model_version"), "model_version")
    _require_sha256(metadata.get("sha256"), "sha256")

    size = _require_positive_int(metadata.get("size"), "size")
    chunks = _require_positive_int(metadata.get("chunks"), "chunks")
    chunk_size = _require_positive_int(metadata.get("chunk_size"), "chunk_size")
    count = _require_positive_int(metadata.get("count"), "count")
    dtype = metadata.get("dtype")
    if dtype not in SUPPORTED_DTYPES:
        raise ValueError(f"unsupported dtype {dtype!r}")
    if size != count * _SUPPORTED_DTYPE_SIZES[dtype]:
        raise ValueError(
            f"size {size} does not match count {count} for dtype {dtype}"
        )
    expected_chunks = chunk_count(size, chunk_size)
    if chunks != expected_chunks:
        raise ValueError(
            f"chunks must be {expected_chunks} for {size} bytes at "
            f"{chunk_size} bytes; got {chunks}"
        )

    kind = metadata.get("kind")
    if kind not in {"model", "dummy"}:
        raise ValueError("kind must be 'model' or 'dummy'")
    model_config = metadata.get("model")
    if not isinstance(model_config, dict):
        raise TypeError("model must be a JSON object")
    if kind == "model":
        for key in ("window_hours", "n_features", "pool_size"):
            if key not in model_config:
                raise ValueError(f"model config is missing {key!r}")
        for key in ("window_hours", "n_features", "pool_size"):
            _require_positive_int(model_config[key], f"model.{key}")

    if message_type == "update_meta":
        _require_positive_int(metadata.get("round"), "round")
    elif "round" in metadata:
        raise ValueError("announce metadata must not carry round")

    prediction_sha = metadata.get("prediction_sha256")
    if prediction_sha is not None:
        _require_sha256(prediction_sha, "prediction_sha256")
    sample = metadata.get("prediction_sample")
    if sample is not None and (
        not isinstance(sample, list)
        or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in sample
        )
    ):
        raise ValueError("prediction_sample must be a list of numbers")


def build_chunk_message(
    metadata: dict[str, Any], index: int, chunk: bytes
) -> dict[str, Any]:
    """Build one sequenced chunk message with its own SHA-256."""
    validate_transfer_metadata(metadata)
    if isinstance(index, bool) or not isinstance(index, int):
        raise TypeError("chunk index must be an integer")
    if index < 0 or index >= metadata["chunks"]:
        raise ValueError(
            f"chunk index {index} out of range for {metadata['chunks']} chunks"
        )
    if not isinstance(chunk, (bytes, bytearray)):
        raise TypeError("chunk must be bytes")
    payload = bytes(chunk)
    expected_size = _expected_chunk_size(metadata, index)
    if len(payload) != expected_size:
        raise ValueError(
            f"chunk {index} has {len(payload)} bytes; expected {expected_size}"
        )
    fields: dict[str, Any] = {
        "message_type": "chunk",
        "model_version": metadata["model_version"],
        "index": index,
        "chunks": metadata["chunks"],
        "chunk_sha256": sha256_hex(payload),
        "size": len(payload),
        "data": base64.b64encode(payload).decode("ascii"),
    }
    if "round" in metadata:
        fields["round"] = metadata["round"]
    return make_message(metadata["node_id"], **fields)


def decode_chunk_message(
    message: dict[str, Any],
    *,
    expected_node_id: str | None = None,
) -> tuple[int, int, bytes]:
    """Validate a chunk message and return ``(index, total_chunks, payload)``."""
    validate_header(message, expected_node_id=expected_node_id)
    if message.get("message_type") != "chunk":
        raise TransferError("not a chunk message")
    index = message.get("index")
    chunks = message.get("chunks")
    if isinstance(index, bool) or not isinstance(index, int):
        raise TransferError("chunk index must be an integer")
    if isinstance(chunks, bool) or not isinstance(chunks, int) or chunks <= 0:
        raise TransferError("chunks must be a positive integer")
    if index < 0 or index >= chunks:
        raise TransferError(f"chunk index {index} out of range for {chunks} chunks")
    encoded = message.get("data")
    if not isinstance(encoded, str):
        raise TransferError("chunk data must be a base64 string")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TransferError(f"chunk data is not valid base64: {exc}") from exc
    if message.get("size") != len(payload):
        raise TransferError(
            f"chunk size mismatch: field says {message.get('size')}, "
            f"decoded {len(payload)}"
        )
    expected_sha = _require_sha256(message.get("chunk_sha256"), "chunk_sha256")
    actual_sha = sha256_hex(payload)
    if actual_sha != expected_sha:
        raise TransferError(
            f"chunk checksum mismatch at index {index}: "
            f"expected {expected_sha}, got {actual_sha}"
        )
    return index, chunks, payload


class WeightReceiver:
    """Collect one transfer, tolerate identical QoS 1 duplicates, reject the rest.

    Out-of-order chunks are accepted.  A conflicting duplicate, a bad chunk
    checksum, an out-of-range index, or a topic/payload disagreement marks the
    transfer as failed.  ``finalize`` additionally rejects missing chunks and
    any whole-payload checksum mismatch.
    """

    def __init__(self, metadata: dict[str, Any]) -> None:
        validate_transfer_metadata(metadata)
        self.metadata = metadata
        self._assembler = ChunkAssembler(metadata["chunks"], metadata["sha256"])
        self._seen: dict[int, bytes] = {}
        self.fatal_error: str | None = None
        self.duplicates_ignored = 0

    @property
    def received_chunks(self) -> int:
        return len(self._seen)

    @property
    def missing_indices(self) -> list[int]:
        return self._assembler.missing_indices

    @property
    def complete(self) -> bool:
        return self._assembler.complete

    def reject(self, reason: str) -> None:
        """Mark the transfer failed; later chunks are refused."""
        if self.fatal_error is None:
            self.fatal_error = reason

    def accept_chunk(
        self,
        index: int,
        chunk: bytes,
        *,
        chunk_sha256: str | None = None,
        topic_index: int | None = None,
        total_chunks: int | None = None,
    ) -> str:
        """Accept one chunk and return ``"added"`` or ``"duplicate"``."""
        if self.fatal_error is not None:
            raise TransferError(f"transfer already rejected: {self.fatal_error}")
        try:
            if isinstance(index, bool) or not isinstance(index, int):
                raise TransferError("chunk index must be an integer")
            if topic_index is not None and topic_index != index:
                raise TransferError(
                    f"topic index {topic_index} disagrees with message index {index}"
                )
            if total_chunks is not None and total_chunks != self.metadata["chunks"]:
                raise TransferError(
                    f"total_chunks {total_chunks} disagrees with metadata "
                    f"{self.metadata['chunks']}"
                )
            if not isinstance(chunk, (bytes, bytearray)):
                raise TransferError("chunk payload must be bytes")
            if index < 0 or index >= self.metadata["chunks"]:
                raise TransferError(
                    f"chunk index {index} out of range for "
                    f"{self.metadata['chunks']} chunks"
                )
            payload = bytes(chunk)
            expected_size = _expected_chunk_size(self.metadata, index)
            if len(payload) != expected_size:
                raise TransferError(
                    f"chunk {index} has {len(payload)} bytes; "
                    f"expected {expected_size}"
                )
            actual_sha = sha256_hex(payload)
            if chunk_sha256 is not None and chunk_sha256.lower() != actual_sha:
                raise TransferError(
                    f"chunk checksum mismatch at index {index}: "
                    f"expected {chunk_sha256}, got {actual_sha}"
                )
            if index in self._seen:
                if self._seen[index] == payload:
                    self.duplicates_ignored += 1
                    return "duplicate"
                raise TransferError(f"conflicting duplicate chunk at index {index}")
            self._assembler.add(index, payload)
            self._seen[index] = payload
            return "added"
        except (ChunkError, TransferError, ValueError) as exc:
            self.reject(str(exc))
            raise TransferError(str(exc)) from exc

    def finalize(self) -> bytes:
        """Join the chunks, verify size and SHA-256, and return the payload."""
        if self.fatal_error is not None:
            raise TransferError(f"transfer already rejected: {self.fatal_error}")
        try:
            payload = self._assembler.reassemble()
            if len(payload) != self.metadata["size"]:
                raise TransferError(
                    f"payload size mismatch: metadata says {self.metadata['size']}, "
                    f"got {len(payload)}"
                )
            return payload
        except (ChunkError, TransferError, ValueError) as exc:
            self.reject(str(exc))
            raise TransferError(str(exc)) from exc


def build_ack_message(
    metadata: dict[str, Any],
    *,
    status: str,
    reason: str | None = None,
    chunks_received: int = 0,
    missing: list[int] | None = None,
    predictions_match: bool | None = None,
) -> dict[str, Any]:
    """Build the server ack for one node update; never includes sensor readings."""
    if status not in {"accepted", "rejected"}:
        raise ValueError("status must be 'accepted' or 'rejected'")
    fields: dict[str, Any] = {
        "message_type": "ack",
        "target_node": metadata["node_id"],
        "round": metadata.get("round"),
        "model_version": metadata["model_version"],
        "sha256": metadata["sha256"],
        "chunks": metadata["chunks"],
        "chunks_received": int(chunks_received),
        "status": status,
        "reason": reason,
        "missing": list(missing or []),
        "predictions_match": predictions_match,
    }
    return make_message("flserver", **fields)


def prediction_probe(
    window_hours: int, n_features: int, *, seed: int = 42, samples: int = 4
) -> np.ndarray:
    """Deterministic input used to compare predictions before/after a transfer."""
    window_hours = _require_positive_int(window_hours, "window_hours")
    n_features = _require_positive_int(n_features, "n_features")
    samples = _require_positive_int(samples, "samples")
    rng = np.random.default_rng(int(seed))
    return rng.uniform(0.0, 1.0, size=(samples, window_hours, n_features)).astype(
        np.float32
    )


def prediction_sample(predictions: np.ndarray, limit: int = 8) -> list[float]:
    """Small prediction fingerprint carried in metadata for a receiver check."""
    values = np.asarray(predictions, dtype=np.float32).reshape(-1)
    return [float(value) for value in values[:limit]]


def prediction_digest(predictions: np.ndarray) -> str:
    """SHA-256 of a float32 prediction vector."""
    values = np.asarray(predictions, dtype=np.float32)
    return sha256_hex(values.tobytes(order="C"))


def _normalize_base_topic(base_topic: str) -> str:
    if not isinstance(base_topic, str) or not base_topic.strip("/"):
        raise ValueError("base_topic must be a non-empty string")
    base = base_topic.strip("/")
    if any(part in {"+", "#"} for part in base.split("/")):
        raise ValueError("base_topic must not contain MQTT wildcards")
    return base


def fl_topic(base_topic: str, *parts: str) -> str:
    """Join a validated Stage 3 topic below the configured base topic."""
    base = _normalize_base_topic(base_topic)
    safe_parts = [_require_safe_token(part, "topic part") for part in parts]
    return "/".join([base, *safe_parts])


def global_announce_topic(base_topic: str) -> str:
    return fl_topic(base_topic, "fl", "global", "announce")


def global_chunk_topic(base_topic: str, index: int) -> str:
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("chunk index must be a non-negative integer")
    return fl_topic(base_topic, "fl", "global", "chunk", str(index))


def global_chunk_filter(base_topic: str) -> str:
    return fl_topic(base_topic, "fl", "global", "chunk") + "/+"


def round_update_meta_topic(base_topic: str, round_number: int, node_id: str) -> str:
    round_number = _require_positive_int(round_number, "round_number")
    _require_safe_token(node_id, "node_id")
    return fl_topic(
        base_topic, "fl", "round", str(round_number), "update", node_id, "meta"
    )


def round_update_chunk_topic(
    base_topic: str, round_number: int, node_id: str, index: int
) -> str:
    round_number = _require_positive_int(round_number, "round_number")
    _require_safe_token(node_id, "node_id")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise ValueError("chunk index must be a non-negative integer")
    return fl_topic(
        base_topic,
        "fl",
        "round",
        str(round_number),
        "update",
        node_id,
        "chunk",
        str(index),
    )


def round_update_meta_filter(base_topic: str) -> str:
    return fl_topic(base_topic, "fl", "round") + "/+/update/+/meta"


def round_update_chunk_filter(base_topic: str) -> str:
    return fl_topic(base_topic, "fl", "round") + "/+/update/+/chunk/+"


def round_ack_topic(base_topic: str, round_number: int, node_id: str) -> str:
    round_number = _require_positive_int(round_number, "round_number")
    _require_safe_token(node_id, "node_id")
    return fl_topic(base_topic, "fl", "round", str(round_number), "ack", node_id)


def parse_global_chunk_topic(topic: str, base_topic: str) -> int | None:
    """Return the chunk index from ``aq/fl/global/chunk/{i}``, or None."""
    pattern = re.compile(
        rf"^{re.escape(_normalize_base_topic(base_topic))}/fl/global/chunk/([0-9]+)$"
    )
    match = pattern.match(topic)
    return int(match.group(1)) if match else None


def parse_round_update_meta_topic(
    topic: str, base_topic: str
) -> tuple[int, str] | None:
    """Return ``(round, node_id)`` from a round update meta topic, or None."""
    pattern = re.compile(
        rf"^{re.escape(_normalize_base_topic(base_topic))}/fl/round/([0-9]+)/update/([^/]+)/meta$"
    )
    match = pattern.match(topic)
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def parse_round_update_chunk_topic(
    topic: str, base_topic: str
) -> tuple[int, str, int] | None:
    """Return ``(round, node_id, index)`` from an update chunk topic, or None."""
    pattern = re.compile(
        rf"^{re.escape(_normalize_base_topic(base_topic))}/fl/round/([0-9]+)/update/"
        r"([^/]+)/chunk/([0-9]+)$"
    )
    match = pattern.match(topic)
    if not match:
        return None
    return int(match.group(1)), match.group(2), int(match.group(3))


def split_weight_payload(
    payload: bytes, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[bytes]:
    """Expose the existing chunk splitter with the Stage 3 default size."""
    return split_payload(payload, chunk_size)
