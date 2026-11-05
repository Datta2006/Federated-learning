"""Small paho-mqtt helpers shared by the server and node clients.

Works with paho-mqtt 1.x and 2.x by selecting the callback API when available.
The actual broker lifecycle lives in the server/node components; these helpers
only create clients, stamp JSON messages, and serialize/deserialize payloads.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string with a trailing Z."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def reason_code_value(reason_code: Any) -> int:
    """Return the integer code from a paho v1 or v2 reason code."""
    return int(getattr(reason_code, "value", reason_code))


def create_client(
    client_id: str,
    host: str,
    port: int,
    *,
    username: str | None = None,
    password: str | None = None,
    keepalive: int = 60,
    clean_session: bool = True,
) -> mqtt.Client:
    """Create a paho client that works on both v1 and v2 APIs."""
    try:
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=clean_session,
            protocol=mqtt.MQTTv311,
        )
    except (AttributeError, TypeError):
        client = mqtt.Client(
            client_id=client_id,
            clean_session=clean_session,
            protocol=mqtt.MQTTv311,
        )

    if username is not None:
        client.username_pw_set(username, password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    # Host/port/keepalive are supplied again to client.connect(); do not put
    # private paho attributes on the client just to cache them.
    return client


def node_topic(base_topic: str, node_id: str, leaf: str) -> str:
    """Build a topic such as ``aq/node1/status`` without double slashes."""
    parts = [part.strip("/") for part in (base_topic, node_id, leaf)]
    if any(not part for part in parts):
        raise ValueError("base_topic, node_id, and leaf must be non-empty")
    if any("/" in part for part in parts[1:]):
        raise ValueError("node_id and leaf must not contain slashes")
    return "/".join(parts)


def make_message(node_id: str, **fields: Any) -> dict[str, Any]:
    """Add the required schema_version, node_id, and UTC ts to a payload."""
    message: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "node_id": node_id,
        "ts": utc_now_iso(),
    }
    message.update(fields)
    return message


def dumps(message: dict[str, Any]) -> str:
    """Serialize a JSON message without NaN/Infinity values."""
    return json.dumps(message, separators=(",", ":"), allow_nan=False)


def loads(payload: bytes | bytearray | str) -> dict[str, Any]:
    """Parse a JSON object payload into a dictionary."""
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode("utf-8")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise TypeError("MQTT JSON payload must be an object")
    return parsed


def publish_json(
    client: mqtt.Client,
    topic: str,
    message: dict[str, Any],
    *,
    qos: int = 1,
    retain: bool = False,
) -> mqtt.MQTTMessageInfo:
    """Publish a JSON object and return paho's message info."""
    return client.publish(topic, dumps(message), qos=qos, retain=retain)


def configure_last_will(
    client: mqtt.Client,
    topic: str,
    payload: dict[str, Any],
    *,
    qos: int = 1,
    retain: bool = True,
) -> None:
    """Set the retained offline status that the broker publishes on LWT."""
    client.will_set(topic, dumps(payload), qos=qos, retain=retain)
