"""Explicit dashboard -> coordinator control publisher.

The dashboard is normally read-only over MQTT.  Control is kept in this one
small adapter so telemetry parsing stays publish-free and every command is
visible and auditable.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

import paho.mqtt.client as mqtt

from common.mqtt_utils import create_client, publish_json, reason_code_value
from common.worker_protocol import build_control, control_topic

LOGGER = logging.getLogger(__name__)


class ControlError(RuntimeError):
    """Raised when a control command cannot be delivered."""


class ControlPublisher:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        base_topic: str,
        qos: int = 1,
        timeout: float = 6.0,
    ) -> None:
        self.host = host
        self.port = port
        self.base_topic = base_topic
        self.qos = qos
        self.timeout = float(timeout)

    def publish(
        self,
        command: str,
        *,
        config: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        message = build_control(command, config=config, **extra)
        connected = threading.Event()

        def on_connect(
            client: mqtt.Client,
            userdata: Any,
            flags: Any,
            reason_code: Any,
            properties: Any = None,
        ) -> None:
            del client, userdata, flags, properties
            if reason_code_value(reason_code) == 0:
                connected.set()

        client = create_client(
            f"airfed-dashboard-control-{uuid.uuid4().hex[:8]}",
            self.host,
            self.port,
            keepalive=15,
        )
        client.on_connect = on_connect
        try:
            client.connect(self.host, self.port, 15)
            client.loop_start()
            if not connected.wait(timeout=self.timeout):
                raise ControlError(
                    f"could not connect to broker {self.host}:{self.port}"
                )
            info = publish_json(
                client,
                control_topic(self.base_topic),
                message,
                qos=self.qos,
                retain=False,
            )
            info.wait_for_publish(timeout=self.timeout)
        except OSError as exc:
            raise ControlError(f"broker unavailable: {exc}") from exc
        except RuntimeError as exc:
            raise ControlError(f"control publish failed: {exc}") from exc
        finally:
            try:
                client.disconnect()
                client.loop_stop()
            except Exception:  # pragma: no cover - best effort
                LOGGER.debug("control client teardown failed", exc_info=True)
        return message


__all__ = ["ControlError", "ControlPublisher"]
