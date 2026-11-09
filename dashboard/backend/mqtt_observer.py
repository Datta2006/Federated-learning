"""Separate read-only paho adapter that feeds :class:`TelemetryStore`.

The observer is deliberately independent of the FL coordinator: a distinct
client id, its own network loop, QoS configured from the project, and no
publish calls.  If the broker is down the API stays up and reports the error.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from common.mqtt_utils import create_client, reason_code_value

from .telemetry import TelemetryStore

LOGGER = logging.getLogger(__name__)


class MQTTObserver:
    def __init__(
        self,
        store: TelemetryStore,
        *,
        host: str,
        port: int,
        client_id: str,
        base_topic: str,
        qos: int = 1,
        keepalive: int = 30,
        enabled: bool = True,
    ) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.client_id = client_id
        self.base_topic = base_topic.strip("/")
        self.qos = qos
        self.keepalive = keepalive
        self.enabled = enabled
        self._stop = threading.Event()
        self._connected = threading.Event()
        self._messages: queue.Queue[tuple[str, bytes, bool]] = queue.Queue(maxsize=4096)
        self._thread: threading.Thread | None = None
        self._worker: threading.Thread | None = None
        self._client: mqtt.Client | None = None

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="airfed-mqtt-observer", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        client = self._client
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # pragma: no cover - best effort shutdown
                pass
            try:
                client.loop_stop()
            except Exception:  # pragma: no cover
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self._worker is not None:
            self._worker.join(timeout=2.0)

    def _run(self) -> None:
        backoff = 1.0
        while not self._stop.is_set():
            try:
                client = create_client(
                    self.client_id,
                    self.host,
                    self.port,
                    keepalive=self.keepalive,
                )
                client.on_connect = self._on_connect
                client.on_disconnect = self._on_disconnect
                client.on_message = self._on_message
                try:
                    client.max_inflight_messages_set(40)
                    client.max_queued_messages_set(0)
                except AttributeError:  # pragma: no cover - paho v1 fallback
                    pass
                self._client = client
                client.connect(self.host, self.port, self.keepalive)
                client.loop_start()
                if not self._connected.wait(timeout=10.0):
                    raise TimeoutError("MQTT connection was not confirmed")
                break
            except Exception as exc:  # noqa: BLE001 - keep API alive
                self.store.set_broker_state(False, error=str(exc))
                LOGGER.warning(
                    "dashboard broker unavailable at %s:%s (%s); retry in %.1fs",
                    self.host,
                    self.port,
                    exc,
                    backoff,
                )
                self._stop.wait(backoff)
                backoff = min(backoff * 2.0, 30.0)

        if self._stop.is_set():
            return

        self._worker = threading.Thread(
            target=self._drain_messages, name="airfed-mqtt-drain", daemon=True
        )
        self._worker.start()

        while not self._stop.is_set():
            self._stop.wait(0.5)

        client = self._client
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # pragma: no cover
                pass
            try:
                client.loop_stop()
            except Exception:  # pragma: no cover
                pass

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any = None,
    ) -> None:
        del userdata, flags, properties
        code = reason_code_value(reason_code)
        if code != 0:
            self.store.set_broker_state(False, error=f"connect rejected ({reason_code})")
            return
        client.subscribe(f"{self.base_topic}/#", qos=self.qos)
        self.store.set_broker_state(True)
        self._connected.set()
        LOGGER.info(
            "dashboard observer connected to %s:%s as %s",
            self.host,
            self.port,
            self.client_id,
        )

    def _on_disconnect(
        self, client: mqtt.Client, userdata: Any, *args: Any
    ) -> None:
        del client, userdata
        reason_code = args[1] if len(args) >= 2 else (args[0] if args else None)
        code = reason_code_value(reason_code) if reason_code is not None else None
        self._connected.clear()
        if code == 0:
            self.store.set_broker_state(False, error=None)
        else:
            self.store.set_broker_state(
                False, error=f"disconnected unexpectedly ({reason_code})"
            )

    def _on_message(
        self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage
    ) -> None:
        del client, userdata
        try:
            self._messages.put_nowait(
                (message.topic, bytes(message.payload), bool(message.retain))
            )
        except queue.Full:  # pragma: no cover - protect the network thread
            LOGGER.warning("dashboard observation queue full; dropping one message")

    def _drain_messages(self) -> None:
        while not self._stop.is_set():
            try:
                topic, payload, retain = self._messages.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.store.ingest(topic, payload, retain=retain)
            except Exception:  # pragma: no cover - never kill the observer
                LOGGER.exception("failed to ingest MQTT message on %s", topic)


def build_observer(store: TelemetryStore, settings: Any) -> MQTTObserver:
    return MQTTObserver(
        store,
        host=settings.broker_host,
        port=settings.broker_port,
        client_id=settings.broker_client_id,
        base_topic=settings.base_topic,
        qos=settings.mqtt_qos,
        enabled=settings.mqtt_enabled,
    )
