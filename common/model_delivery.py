"""Retained global-model delivery with version-aware late-joiner support.

The server publishes one retained announce plus one retained message per chunk
topic.  MQTT keeps the latest message on each topic, so a node or the phone can
subscribe at any time and reconstruct the current global model without the
server tracking subscribers or running a ready handshake.

Chunks carry ``model_version``.  The receiver buffers chunks that arrive before
their announce, only assembles the newest announced version, and ignores stale
retained chunks from an older version.  This is the seam that makes late
joiners safe even when retained messages arrive in an arbitrary order.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import paho.mqtt.client as mqtt

from common.federated import is_newer_version, model_version_number
from common.mqtt_utils import dumps, loads, publish_json
from common.weight_transfer import (
    DEFAULT_CHUNK_SIZE,
    TransferError,
    WeightReceiver,
    build_chunk_message,
    build_transfer_metadata,
    decode_chunk_message,
    decode_weights,
    encode_weights,
    global_announce_topic,
    global_chunk_topic,
    parse_global_chunk_topic,
    split_weight_payload,
    validate_header,
    validate_transfer_metadata,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedModel:
    """One built (and optionally published) global model."""

    metadata: dict[str, Any]
    chunks: list[bytes]
    chunk_messages: list[dict[str, Any]]
    chunk_topics: list[str]
    bytes: int


@dataclass(frozen=True)
class ReceivedModel:
    """A complete global model reconstructed by a subscriber."""

    metadata: dict[str, Any]
    weights: np.ndarray


class GlobalModelPublisher:
    """Build and publish a retained global model for current and late nodes."""

    def __init__(
        self,
        client: mqtt.Client | None,
        base_topic: str,
        *,
        qos: int = 1,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        retain: bool = True,
        wait: bool = True,
        wait_timeout: float = 10.0,
    ) -> None:
        self.client = client
        self.base_topic = base_topic
        self.qos = qos
        self.chunk_size = chunk_size
        self.retain = retain
        self.wait = wait
        self.wait_timeout = wait_timeout

    def build(
        self,
        weights: np.ndarray,
        *,
        model_version: str,
        model_config: dict[str, Any],
        kind: str = "model",
        extra_fields: dict[str, Any] | None = None,
    ) -> PublishedModel:
        """Build the announce and chunk messages without touching the broker."""
        metadata = build_transfer_metadata(
            weights,
            node_id="flserver",
            model_version=model_version,
            model_config=model_config,
            kind=kind,
            chunk_size=self.chunk_size,
        )
        if extra_fields:
            metadata.update(extra_fields)
        validate_transfer_metadata(metadata)
        payload = encode_weights(weights)
        chunks = split_weight_payload(payload, self.chunk_size)
        chunk_messages = [
            build_chunk_message(metadata, index, chunk)
            for index, chunk in enumerate(chunks)
        ]
        chunk_topics = [
            global_chunk_topic(self.base_topic, index) for index in range(len(chunks))
        ]
        total_bytes = len(dumps(metadata).encode("utf-8")) + sum(
            len(dumps(message).encode("utf-8")) for message in chunk_messages
        )
        return PublishedModel(
            metadata=metadata,
            chunks=chunks,
            chunk_messages=chunk_messages,
            chunk_topics=chunk_topics,
            bytes=total_bytes,
        )

    def publish(
        self,
        weights: np.ndarray,
        *,
        model_version: str,
        model_config: dict[str, Any],
        kind: str = "model",
        extra_fields: dict[str, Any] | None = None,
    ) -> PublishedModel:
        """Publish the announce first, then every chunk, retaining each topic."""
        if self.client is None:
            raise ValueError("publish() requires an MQTT client")
        published = self.build(
            weights,
            model_version=model_version,
            model_config=model_config,
            kind=kind,
            extra_fields=extra_fields,
        )
        announce = publish_json(
            self.client,
            global_announce_topic(self.base_topic),
            published.metadata,
            qos=self.qos,
            retain=self.retain,
        )
        if self.wait:
            announce.wait_for_publish(timeout=self.wait_timeout)
        for topic, message in zip(
            published.chunk_topics, published.chunk_messages, strict=True
        ):
            info = publish_json(
                self.client, topic, message, qos=self.qos, retain=self.retain
            )
            if self.wait:
                info.wait_for_publish(timeout=self.wait_timeout)
        return published


class GlobalModelReceiver:
    """Version-aware receiver for retained announce + retained chunk streams."""

    def __init__(self, base_topic: str, *, expected_node_id: str = "flserver") -> None:
        self.base_topic = base_topic
        self.expected_node_id = expected_node_id
        self._announces: dict[str, dict[str, Any]] = {}
        self._receivers: dict[str, WeightReceiver] = {}
        self._buffered: dict[str, dict[int, dict[str, Any]]] = {}
        self._returned: set[str] = set()
        self.latest_version: str | None = None
        self.last_error: str | None = None
        self.bytes_received = 0

    @property
    def latest_metadata(self) -> dict[str, Any] | None:
        if self.latest_version is None:
            return None
        return self._announces.get(self.latest_version)

    def handle_message(
        self, topic: str, payload: bytes | bytearray | str | dict[str, Any]
    ) -> ReceivedModel | None:
        """Consume one announce or chunk; return a model when it completes."""
        if isinstance(payload, (bytes, bytearray)):
            self.bytes_received += len(payload)
            message = loads(payload)
        elif isinstance(payload, str):
            self.bytes_received += len(payload.encode("utf-8"))
            message = loads(payload)
        else:
            message = payload

        if topic == global_announce_topic(self.base_topic):
            return self._handle_announce(message)
        index = parse_global_chunk_topic(topic, self.base_topic)
        if index is not None:
            return self._handle_chunk(index, message)
        return None

    def _handle_announce(self, message: dict[str, Any]) -> ReceivedModel | None:
        try:
            validate_header(message, expected_node_id=self.expected_node_id)
            if message.get("message_type") != "announce":
                raise TransferError("global announce has the wrong message_type")
            validate_transfer_metadata(message)
        except (TypeError, ValueError, TransferError) as exc:
            self.last_error = str(exc)
            LOGGER.warning("ignoring bad global announce: %s", exc)
            return None

        version = str(message["model_version"])
        existing = self._announces.get(version)
        if version == self.latest_version:
            if existing is not None and existing["sha256"] == message["sha256"]:
                # A repeated retained announce for the same payload; the
                # receiver may already have completed it.
                return None
            self._receivers[version] = WeightReceiver(message)
            self._returned.discard(version)
        elif is_newer_version(version, self.latest_version):
            self.latest_version = version
            self._drop_older_than(version)
            self._receivers[version] = WeightReceiver(message)
            self._returned.discard(version)
        else:
            LOGGER.info("ignoring stale global announce %s", version)
            return None

        self._announces[version] = message
        buffered = sorted(self._buffered.pop(version, {}).items())
        result: ReceivedModel | None = None
        for _index, chunk_message in buffered:
            completed = self._feed_chunk(version, chunk_message)
            if completed is not None:
                result = completed
        return result

    def _handle_chunk(self, index: int, message: dict[str, Any]) -> ReceivedModel | None:
        try:
            validate_header(message)
            if message.get("message_type") != "chunk":
                raise TransferError("not a chunk message")
            version = message.get("model_version")
            if not isinstance(version, str) or not version:
                raise TransferError("chunk is missing model_version")
            if message.get("index") != index:
                raise TransferError("chunk topic index disagrees with the message")
        except (TypeError, ValueError, TransferError) as exc:
            self.last_error = str(exc)
            LOGGER.warning("ignoring bad global chunk: %s", exc)
            return None

        if self.latest_version is not None and version != self.latest_version:
            if not is_newer_version(version, self.latest_version):
                return None
            # A newer chunk arrived before its announce; keep it until the
            # retained announce is delivered.
            self._buffered.setdefault(version, {})[index] = message
            return None
        if version not in self._announces:
            self._buffered.setdefault(version, {})[index] = message
            return None
        return self._feed_chunk(version, message)

    def _feed_chunk(
        self, version: str, message: dict[str, Any]
    ) -> ReceivedModel | None:
        receiver = self._receivers.get(version)
        if receiver is None:
            announce = self._announces.get(version)
            if announce is None:
                return None
            receiver = WeightReceiver(announce)
            self._receivers[version] = receiver
        try:
            index, total_chunks, chunk = decode_chunk_message(
                message, expected_node_id=self.expected_node_id
            )
            if message.get("model_version") != version:
                raise TransferError("chunk model_version disagrees with the announce")
            receiver.accept_chunk(
                index,
                chunk,
                chunk_sha256=message["chunk_sha256"],
                topic_index=index,
                total_chunks=total_chunks,
            )
            if receiver.complete and version not in self._returned:
                payload = receiver.finalize()
                weights = decode_weights(
                    payload,
                    str(receiver.metadata["dtype"]),
                    int(receiver.metadata["count"]),
                )
                self._returned.add(version)
                return ReceivedModel(metadata=self._announces[version], weights=weights)
        except (TypeError, ValueError, TransferError) as exc:
            self.last_error = str(exc)
            LOGGER.warning("rejected global chunk for %s: %s", version, exc)
        return None

    def _drop_older_than(self, version: str) -> None:
        latest_number = model_version_number(version)
        if latest_number is None:
            return
        for name in list(self._announces):
            number = model_version_number(name)
            if number is not None and number < latest_number:
                self._announces.pop(name, None)
                self._receivers.pop(name, None)
                self._buffered.pop(name, None)
                self._returned.discard(name)
