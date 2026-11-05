"""Stage 2 MQTT server: observe retained node status, heartbeats, and LWTs."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

from common.config import load_config
from common.mqtt_utils import create_client, loads, reason_code_value

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


def _node_from_topic(topic: str, base_topic: str) -> str | None:
    prefix = f"{base_topic.strip('/')}/"
    if not topic.startswith(prefix):
        return None
    remainder = topic[len(prefix) :]
    node_id, _, _leaf = remainder.partition("/")
    return node_id or None


def run(
    config_path: str | Path | None = None,
    *,
    run_seconds: float | None = None,
) -> int:
    """Subscribe to status/health topics and print online/offline transitions."""
    STOP.clear()
    config = load_config(config_path)
    mqtt_cfg = config["mqtt"]
    host = str(mqtt_cfg["host"])
    port = int(mqtt_cfg["port"])
    qos = int(mqtt_cfg["qos"])
    keepalive = int(mqtt_cfg["keepalive"])
    base_topic = str(mqtt_cfg["base_topic"])
    status_filter = f"{base_topic}/+/status"
    health_filter = f"{base_topic}/+/health"

    client = create_client("fl-server", host, port, keepalive=keepalive)
    seen_status: dict[str, str] = {}

    def on_connect(
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        code = reason_code_value(reason_code)
        if code != 0:
            LOGGER.error("connect failed: %s", reason_code)
            return
        LOGGER.info("connected to %s:%s", host, port)
        client.subscribe([(status_filter, qos), (health_filter, qos)])

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        del client, userdata
        try:
            payload = loads(message.payload)
        except (ValueError, TypeError) as exc:
            LOGGER.warning("bad JSON on %s: %s", message.topic, exc)
            return
        node_id = _node_from_topic(message.topic, base_topic)
        if node_id is None:
            LOGGER.warning("unexpected topic %s", message.topic)
            return
        leaf = message.topic.rsplit("/", 1)[-1]
        if leaf == "status":
            state = str(payload.get("state", "unknown"))
            seen_status[node_id] = state
            retained = " retained" if message.retain else ""
            reason = payload.get("reason")
            detail = f" reason={reason}" if reason else ""
            print(
                f"status {node_id}: {state}{retained}{detail} at {payload.get('ts')}",
                flush=True,
            )
        elif leaf == "health":
            print(
                f"health {node_id}: backend={payload.get('backend')} "
                f"uptime={payload.get('uptime_sec')}s at {payload.get('ts')}",
                flush=True,
            )

    def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        LOGGER.warning("disconnected from broker (%s); paho will reconnect", reason_code)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    backoff = 1.0
    while not STOP.is_set():
        try:
            client.connect(host, port, keepalive)
            break
        except OSError as exc:
            LOGGER.warning("broker unavailable at %s:%s (%s); retry in %.1fs", host, port, exc, backoff)
            STOP.wait(backoff)
            backoff = min(backoff * 2.0, 30.0)

    if STOP.is_set():
        return 1

    client.loop_start()
    deadline = time.monotonic() + run_seconds if run_seconds else None
    try:
        while not STOP.is_set():
            if deadline is not None and time.monotonic() >= deadline:
                break
            STOP.wait(0.5)
    except KeyboardInterrupt:
        LOGGER.info("interrupted")
    finally:
        client.disconnect()
        client.loop_stop()
        LOGGER.info("server stopped; last statuses: %s", seen_status)
    return 0


def _main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2 MQTT status server")
    parser.add_argument("--config", default=None)
    parser.add_argument("--run-seconds", type=float, default=None)
    parser.add_argument("--verbose", action="count", default=0)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.verbose == 0 else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def stop_handler(signum: int, frame: Any) -> None:
        del signum, frame
        STOP.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    raise SystemExit(run(args.config, run_seconds=args.run_seconds))


if __name__ == "__main__":
    _main()
