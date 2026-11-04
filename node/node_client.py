"""Stage 2 MQTT node hello-world: retained status, LWT, and health beats.

This is deliberately not the data node yet. It proves the broker lifecycle and
topic contract before dataset replay, predictions, or federated rounds.
"""

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
from common.mqtt_utils import (
    configure_last_will,
    create_client,
    make_message,
    node_topic,
    publish_json,
)

LOGGER = logging.getLogger(__name__)
STOP = threading.Event()


def _reason_code_value(reason_code: Any) -> int:
    return int(getattr(reason_code, "value", reason_code))


def make_status(node_id: str, state: str, reason: str | None = None) -> dict[str, Any]:
    """Build a status payload; ``offline`` is used for the retained LWT."""
    fields: dict[str, Any] = {"state": state}
    if reason is not None:
        fields["reason"] = reason
    return make_message(node_id, **fields)


def make_health(
    node_id: str,
    *,
    backend: str,
    uptime_sec: float,
) -> dict[str, Any]:
    """Build a Stage 2 health payload without inventing sensor readings."""
    return make_message(
        node_id,
        backend=backend,
        uptime_sec=round(uptime_sec, 1),
        battery_pct=None,
        rssi_dbm=None,
        cpu_temp_c=None,
        last_read_age_sec=None,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 2 MQTT node heartbeat")
    parser.add_argument("--config", default=None)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--backend", default="none")
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--keepalive", type=int, default=None)
    parser.add_argument("--run-seconds", type=float, default=None)
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def run(
    config_path: str | Path | None = None,
    *,
    node_id: str,
    backend: str = "none",
    interval: float | None = None,
    keepalive: int | None = None,
    run_seconds: float | None = None,
) -> int:
    """Connect, publish retained online status, heartbeat, and exit cleanly."""
    STOP.clear()
    config = load_config(config_path)
    if node_id not in config["nodes"]:
        raise ValueError(
            f"unknown node_id {node_id!r}; expected one of {sorted(config['nodes'])}"
        )
    mqtt_cfg = config["mqtt"]
    host = str(mqtt_cfg["host"])
    port = int(mqtt_cfg["port"])
    qos = int(mqtt_cfg["qos"])
    keepalive_sec = int(keepalive if keepalive is not None else mqtt_cfg["keepalive"])
    heartbeat_sec = float(
        interval if interval is not None else mqtt_cfg.get("heartbeat_sec", 10)
    )
    if heartbeat_sec <= 0:
        raise ValueError("--interval must be positive")

    base_topic = str(mqtt_cfg["base_topic"])
    status_topic = node_topic(base_topic, node_id, "status")
    health_topic = node_topic(base_topic, node_id, "health")
    client = create_client(f"node-{node_id}", host, port, keepalive=keepalive_sec)
    configure_last_will(
        client,
        status_topic,
        make_status(node_id, "offline", "lwt"),
        qos=qos,
        retain=True,
    )

    process_started = time.monotonic()

    def on_connect(
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        code = _reason_code_value(reason_code)
        if code != 0:
            LOGGER.error("connect failed: %s", reason_code)
            return
        LOGGER.info("connected to %s:%s as %s", host, port, node_id)
        publish_json(
            client,
            status_topic,
            make_status(node_id, "online"),
            qos=qos,
            retain=True,
        )
        publish_json(
            client,
            health_topic,
            make_health(node_id, backend=backend, uptime_sec=time.monotonic() - process_started),
            qos=qos,
            retain=False,
        )

    def on_disconnect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        code = _reason_code_value(reason_code) if reason_code is not None else None
        if code == 0:
            LOGGER.info("disconnected cleanly")
        else:
            LOGGER.warning("disconnected unexpectedly (%s); paho will reconnect", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    backoff = 1.0
    while not STOP.is_set():
        try:
            client.connect(host, port, keepalive_sec)
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
        last_heartbeat = 0.0
        while not STOP.is_set():
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                LOGGER.info("run duration reached; shutting down")
                break
            if client.is_connected() and now - last_heartbeat >= heartbeat_sec:
                publish_json(
                    client,
                    health_topic,
                    make_health(
                        node_id,
                        backend=backend,
                        uptime_sec=now - process_started,
                    ),
                    qos=qos,
                    retain=False,
                )
                last_heartbeat = now
            STOP.wait(min(1.0, heartbeat_sec))
    except KeyboardInterrupt:
        LOGGER.info("interrupted")
    finally:
        if client.is_connected():
            info = publish_json(
                client,
                status_topic,
                make_status(node_id, "offline", "graceful"),
                qos=qos,
                retain=True,
            )
            deadline = time.monotonic() + 2.0
            while not info.is_published() and time.monotonic() < deadline:
                time.sleep(0.05)
            if info.is_published():
                client.disconnect()
            else:
                # Do not send a clean DISCONNECT: if the retained offline
                # publish was not confirmed, the broker's LWT is the fallback.
                LOGGER.warning(
                    "offline status not confirmed; leaving connection for LWT"
                )
        client.loop_stop()
        LOGGER.info("stopped %s", node_id)
    return 0


def _main() -> None:
    args = build_parser().parse_args()
    level = logging.WARNING if args.verbose == 0 else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    def stop_handler(signum: int, frame: Any) -> None:
        del signum, frame
        STOP.set()

    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    raise SystemExit(
        run(
            args.config,
            node_id=args.node_id,
            backend=args.backend,
            interval=args.interval,
            keepalive=args.keepalive,
            run_seconds=args.run_seconds,
        )
    )


if __name__ == "__main__":
    _main()
