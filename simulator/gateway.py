"""Gateway implementation for Resilient IoT Gateway Architecture (Stack 2).

This module implements the Gateway class with six logical components:
1. Sensor Ingestion Component - receives telemetry from sensors via RPL routes
2. Device Manager - manages sensor registry, assignment, and lifecycle
3. Local Storage Component - buffers telemetry during WAN outages with persistence
4. Communication Manager - handles MQTT client for gateway-to-central (airfed/gateways/{id}/telemetry|status|health)
5. Network Monitor - tracks RPL parent reachability, triggers local repair
6. Forwarding Manager - routes sensor packets upward via RPL (compute_upward_route)
"""

from __future__ import annotations

import json
import random
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

from simulator.entities import (
    GatewayNode,
    NetworkNode,
    Position,
    SensorNode,
    SensorReading,
)
import paho.mqtt.client as mqtt
from simulator.rpl import RPLEngine, RPLNodeState
from simulator.topology import NetworkTopology
from simulator.fl_client import FederatedLearningClient
from simulator.fl_storage import FLStorageComponent
from common.mqtt_utils import (
    configure_last_will,
    create_client,
    make_message,
    publish_json,
)


class GatewayStatus(Enum):
    """Gateway operational status."""

    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    RECOVERING = "recovering"


class WANStatus(Enum):
    """WAN (wide-area network) connectivity status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"


@dataclass
class SensorRegistration:
    """Sensor registration record in device manager."""

    node_id: str
    gateway_id: str
    name: str | None = None
    position: Position | None = None
    registered_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    reading_count: int = 0
    is_active: bool = True


@dataclass
class TelemetryBufferEntry:
    """Entry in the local telemetry buffer."""

    sensor_id: str
    reading: SensorReading
    timestamp: float
    forwarded: bool = False
    mqtt_published: bool = False
    attempts: int = 0
    last_attempt: float = 0.0


@dataclass
class CoAPMessage:
    """CoAP-inspired message for sensor-to-gateway communication."""

    class MessageType(Enum):
        CON = 0  # Confirmable
        NON = 1  # Non-confirmable
        ACK = 2  # Acknowledgement
        RST = 3  # Reset

    class Method(Enum):
        GET = 1
        POST = 2
        PUT = 3
        DELETE = 4

    message_id: int
    message_type: MessageType
    method: Method | None = None
    token: bytes = field(default_factory=lambda: random.randbytes(4))
    payload: bytes = b""
    uri_path: str = ""
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create_telemetry_post(
        cls, sensor_id: str, reading: SensorReading, message_id: int
    ) -> "CoAPMessage":
        """Create a CoAP POST for sensor telemetry."""
        payload = json.dumps(reading.to_dict()).encode()
        return cls(
            message_id=message_id,
            message_type=cls.MessageType.CON,
            method=cls.Method.POST,
            uri_path=f"telemetry/{sensor_id}",
            payload=payload,
        )

    @classmethod
    def create_ack(cls, message_id: int, token: bytes) -> "CoAPMessage":
        """Create a CoAP ACK response."""
        return cls(
            message_id=message_id,
            message_type=cls.MessageType.ACK,
            token=token,
        )

    def to_bytes(self) -> bytes:
        """Serialize to simplified CoAP binary format."""
        # Simplified CoAP header: version(2) | type(2) | token_len(4) | code(8) | message_id(16)
        # This is a simplified implementation for simulation purposes
        header = bytearray(4)
        header[0] = 0x40 | (self.message_type.value << 4) | (len(self.token) & 0x0F)
        header[1] = self.method.value if self.method else 0
        header[2] = (self.message_id >> 8) & 0xFF
        header[3] = self.message_id & 0xFF
        return bytes(header) + self.token + self.payload

    @classmethod
    def from_bytes(cls, data: bytes) -> "CoAPMessage":
        """Parse from simplified CoAP binary format."""
        if len(data) < 4:
            raise ValueError("Invalid CoAP message: too short")
        header = data[:4]
        token_len = header[0] & 0x0F
        msg_type = (header[0] >> 4) & 0x03
        code = header[1]
        msg_id = (header[2] << 8) | header[3]
        token = data[4 : 4 + token_len]
        payload = data[4 + token_len :]
        return cls(
            message_id=msg_id,
            message_type=cls.MessageType(msg_type),
            method=cls.Method(code) if code in (1, 2, 3, 4) else None,
            token=token,
            payload=payload,
        )


@dataclass
class NetworkHealthMetrics:
    """Network health metrics for a gateway's DODAG."""

    dodag_id: str
    timestamp: float
    node_count: int
    reachable_nodes: int
    avg_rank: float
    avg_etx: float
    parent_changes: int
    dio_received: int
    dis_sent: int
    dao_sent: int
    routes_up: int
    routes_down: int


class SensorIngestionComponent:
    """Component 1: Receives telemetry from sensors via RPL upward routes."""

    def __init__(self, gateway: "Gateway") -> None:
        self.gateway = gateway
        self.received_count = 0
        self.last_received: dict[str, float] = {}
        self._lock = threading.Lock()

    def receive_telemetry(
        self, sensor_id: str, reading: SensorReading, route: list[str]
    ) -> bool:
        """Receive telemetry from a sensor via RPL route."""
        with self._lock:
            self.received_count += 1
            self.last_received[sensor_id] = time.time()

            # Store in local buffer via storage component
            self.gateway.local_storage.buffer_telemetry(sensor_id, reading)

            # Update device manager
            self.gateway.device_manager.update_sensor_activity(sensor_id)

            return True

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total_received": self.received_count,
                "last_received": self.last_received.copy(),
            }


class DeviceManager:
    """Component 2: Manages sensor registry, assignment, and lifecycle."""

    def __init__(self, gateway: "Gateway") -> None:
        self.gateway = gateway
        self.sensors: dict[str, SensorRegistration] = {}
        self._lock = threading.Lock()

    def register_sensor(
        self,
        node_id: str,
        name: str | None = None,
        position: Position | None = None,
    ) -> SensorRegistration:
        """Register a new sensor with this gateway."""
        with self._lock:
            registration = SensorRegistration(
                node_id=node_id,
                gateway_id=self.gateway.gateway_id,
                name=name,
                position=position,
            )
            self.sensors[node_id] = registration
            return registration

    def unregister_sensor(self, node_id: str) -> bool:
        """Unregister a sensor."""
        with self._lock:
            if node_id in self.sensors:
                self.sensors[node_id].is_active = False
                del self.sensors[node_id]
                return True
            return False

    def get_sensor(self, node_id: str) -> SensorRegistration | None:
        """Get sensor registration."""
        with self._lock:
            return self.sensors.get(node_id)

    def list_sensors(self, active_only: bool = True) -> list[SensorRegistration]:
        """List all registered sensors."""
        with self._lock:
            sensors = list(self.sensors.values())
            if active_only:
                sensors = [s for s in sensors if s.is_active]
            return sensors

    def update_sensor_activity(self, node_id: str) -> None:
        """Update sensor last seen timestamp."""
        with self._lock:
            if node_id in self.sensors:
                self.sensors[node_id].last_seen = time.time()
                self.sensors[node_id].reading_count += 1

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            active = [s for s in self.sensors.values() if s.is_active]
            return {
                "total_registered": len(self.sensors),
                "active": len(active),
                "sensors": {s.node_id: {"last_seen": s.last_seen, "readings": s.reading_count} for s in active},
            }


class LocalStorageComponent:
    """Component 3: Buffers telemetry during WAN outages with persistence."""

    def __init__(
        self,
        gateway: "Gateway",
        max_entries: int = 10000,
        max_size_mb: float = 100.0,
    ) -> None:
        self.gateway = gateway
        self.max_entries = max_entries
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.buffer: deque[TelemetryBufferEntry] = deque(maxlen=max_entries)
        self.current_size_bytes = 0
        self._lock = threading.Lock()
        self.flushed_count = 0
        self.dropped_count = 0

    def buffer_telemetry(self, sensor_id: str, reading: SensorReading) -> bool:
        """Add telemetry to local buffer."""
        with self._lock:
            entry = TelemetryBufferEntry(
                sensor_id=sensor_id,
                reading=reading,
                timestamp=time.time(),
            )
            # Estimate size
            entry_size = len(json.dumps(reading.to_dict()).encode()) + 100

            # Check if we need to evict old entries
            while (
                self.current_size_bytes + entry_size > self.max_size_bytes
                or len(self.buffer) >= self.max_entries
            ) and self.buffer:
                removed = self.buffer.popleft()
                self.current_size_bytes -= len(
                    json.dumps(removed.reading.to_dict()).encode()
                ) + 100
                self.dropped_count += 1

            self.buffer.append(entry)
            self.current_size_bytes += entry_size
            return True

    def get_pending(self, limit: int = 100) -> list[TelemetryBufferEntry]:
        """Get pending (unforwarded) telemetry entries."""
        with self._lock:
            pending = [e for e in self.buffer if not e.forwarded]
            return pending[:limit]

    def mark_forwarded(self, sensor_id: str, timestamp: float) -> bool:
        """Mark entries as forwarded."""
        with self._lock:
            for entry in self.buffer:
                if (
                    entry.sensor_id == sensor_id
                    and abs(entry.timestamp - timestamp) < 0.001
                    and not entry.forwarded
                ):
                    entry.forwarded = True
                    self.flushed_count += 1
                    return True
            return False

    def mark_mqtt_published(self, sensor_id: str, timestamp: float) -> bool:
        """Mark entries as published to MQTT."""
        with self._lock:
            for entry in self.buffer:
                if (
                    entry.sensor_id == sensor_id
                    and abs(entry.timestamp - timestamp) < 0.001
                    and entry.forwarded
                    and not entry.mqtt_published
                ):
                    entry.mqtt_published = True
                    return True
            return False

    def cleanup_old_entries(self, max_age_seconds: float = 3600) -> int:
        """Remove old entries that have been forwarded and published."""
        with self._lock:
            now = time.time()
            removed = 0
            while self.buffer:
                entry = self.buffer[0]
                if (
                    entry.forwarded
                    and entry.mqtt_published
                    and now - entry.timestamp > max_age_seconds
                ):
                    self.buffer.popleft()
                    self.current_size_bytes -= len(
                        json.dumps(entry.reading.to_dict()).encode()
                    ) + 100
                    removed += 1
                else:
                    break
            return removed

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            pending = sum(1 for e in self.buffer if not e.forwarded)
            forwarded_not_published = sum(
                1 for e in self.buffer if e.forwarded and not e.mqtt_published
            )
            return {
                "total_entries": len(self.buffer),
                "pending": pending,
                "forwarded_not_published": forwarded_not_published,
                "flushed_count": self.flushed_count,
                "dropped_count": self.dropped_count,
                "size_bytes": self.current_size_bytes,
                "size_mb": self.current_size_bytes / (1024 * 1024),
                "max_size_mb": self.max_size_bytes / (1024 * 1024),
            }


class CommunicationManager:
    """Component 4: Handles MQTT client for gateway-to-central communication."""

    def __init__(
        self,
        gateway: "Gateway",
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str | None = None,
    ) -> None:
        self.gateway = gateway
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id or f"gateway-{gateway.gateway_id}"
        self.client: mqtt.Client | None = None
        self.connected = False
        self.wan_status = WANStatus.DISCONNECTED
        self._lock = threading.Lock()
        self._message_queue: deque[dict[str, Any]] = deque()
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay = 5.0
        self.stats = {
            "published": 0,
            "failed": 0,
            "reconnects": 0,
        }

    def connect(self) -> bool:
        """Connect to MQTT broker."""
        with self._lock:
            if self.client and self.connected:
                return True

            try:
                self.client = create_client(
                    client_id=self.client_id,
                    host=self.broker_host,
                    port=self.broker_port,
                    keepalive=60,
                    clean_session=True,
                )

                # Set last will for health topic
                configure_last_will(
                    self.client,
                    topic=f"airfed/gateways/{self.gateway.gateway_id}/health",
                    payload=json.dumps(
                        {
                            "gateway_id": self.gateway.gateway_id,
                            "status": "offline",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    ).encode(),
                    qos=1,
                    retain=True,
                )

                # Set callbacks
                self.client.on_connect = self._on_connect
                self.client.on_disconnect = self._on_disconnect
                self.client.on_publish = self._on_publish

                self.client.connect(self.broker_host, self.broker_port, 60)
                self.client.loop_start()
                self.wan_status = WANStatus.RECONNECTING
                return True

            except Exception as e:
                self.stats["failed"] += 1
                self.wan_status = WANStatus.DISCONNECTED
                return False

    def _on_connect(self, client, userdata, flags, rc) -> None:
        """MQTT on_connect callback."""
        if rc == 0:
            with self._lock:
                self.connected = True
                self.wan_status = WANStatus.CONNECTED
                self._reconnect_attempts = 0
                self.stats["reconnects"] += 1
                # Publish online status
                self._publish_status("online")
                # Process queued messages
                self._process_queue()
        else:
            self.wan_status = WANStatus.DISCONNECTED

    def _on_disconnect(self, client, userdata, rc) -> None:
        """MQTT on_disconnect callback."""
        with self._lock:
            self.connected = False
            self.wan_status = WANStatus.DISCONNECTED
            if rc != 0:
                # Unexpected disconnect, attempt reconnect
                self._schedule_reconnect()

    def _on_publish(self, client, userdata, mid) -> None:
        """MQTT on_publish callback."""
        self.stats["published"] += 1

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = self._reconnect_delay * min(self._reconnect_attempts, 5)
            # In a real implementation, this would use a timer
            # For simulation, we'll just note it needs reconnection
            self.wan_status = WANStatus.RECONNECTING

    def _process_queue(self) -> None:
        """Process queued messages."""
        while self._message_queue and self.connected:
            msg = self._message_queue.popleft()
            self._publish_internal(msg["topic"], msg["payload"], msg.get("qos", 1))

    def _publish_internal(self, topic: str, payload: dict[str, Any], qos: int = 1) -> bool:
        """Internal publish (assumes lock held)."""
        if not self.client or not self.connected:
            self._message_queue.append({"topic": topic, "payload": payload, "qos": qos})
            return False

        try:
            result = publish_json(self.client, topic, payload, qos=qos)
            return result.rc == 0
        except Exception:
            self.stats["failed"] += 1
            self._message_queue.append({"topic": topic, "payload": payload, "qos": qos})
            return False

    def publish_telemetry(self, sensor_id: str, reading: SensorReading) -> bool:
        """Publish sensor telemetry to MQTT."""
        topic = f"airfed/gateways/{self.gateway.gateway_id}/telemetry"
        payload = {
            "gateway_id": self.gateway.gateway_id,
            "sensor_id": sensor_id,
            "reading": reading.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self._lock:
            return self._publish_internal(topic, payload)

    def publish_status(self, status: str) -> bool:
        """Publish gateway status."""
        return self._publish_status(status)

    def _publish_status(self, status: str) -> bool:
        """Internal status publish."""
        topic = f"airfed/gateways/{self.gateway.gateway_id}/status"
        payload = {
            "gateway_id": self.gateway.gateway_id,
            "status": status,
            "wan_status": self.wan_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sensor_count": len(self.gateway.device_manager.sensors),
            "buffer_stats": self.gateway.local_storage.get_stats(),
        }
        with self._lock:
            return self._publish_internal(topic, payload, qos=1)

    def publish_health(self, health_data: dict[str, Any]) -> bool:
        """Publish gateway health metrics."""
        topic = f"airfed/gateways/{self.gateway.gateway_id}/health"
        payload = {
            "gateway_id": self.gateway.gateway_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **health_data,
        }
        with self._lock:
            return self._publish_internal(topic, payload, qos=1)

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        with self._lock:
            if self.client:
                self._publish_status("offline")
                self.client.loop_stop()
                self.client.disconnect()
                self.client = None
                self.connected = False
                self.wan_status = WANStatus.DISCONNECTED

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self.connected,
                "wan_status": self.wan_status.value,
                "client_id": self.client_id,
                "broker": f"{self.broker_host}:{self.broker_port}",
                "queued_messages": len(self._message_queue),
                **self.stats,
            }


class NetworkMonitor:
    """Component 5: Tracks RPL parent reachability, triggers local repair."""

    def __init__(self, gateway: "Gateway") -> None:
        self.gateway = gateway
        self.parent_reachability: dict[str, dict[str, Any]] = {}
        self.repair_triggers = 0
        self.repairs_completed = 0
        self.last_check = 0.0
        self._lock = threading.Lock()

    def check_parent_reachability(self, now: float) -> dict[str, Any]:
        """Check reachability of preferred parents for sensors in this DODAG."""
        with self._lock:
            self.last_check = now
            results = {}

            rpl_engine = self.gateway.rpl_engine
            dodag_id = self.gateway.dodag_id

            if not dodag_id or dodag_id not in rpl_engine.dodag_configs:
                return results

            sensors = self.gateway.device_manager.list_sensors()

            for sensor_reg in sensors:
                sensor_id = sensor_reg.node_id
                state = rpl_engine.nodes_state.get(sensor_id)

                if not state or not state.rank or not state.rank.preferred_parent:
                    results[sensor_id] = {
                        "reachable": False,
                        "reason": "no_parent",
                        "parent": None,
                    }
                    continue

                parent_id = state.rank.preferred_parent
                link = self.gateway.topology.get_link_between(sensor_id, parent_id)

                reachable = link is not None and link.available
                results[sensor_id] = {
                    "reachable": reachable,
                    "parent": parent_id,
                    "link_quality": link.quality if link else 0.0,
                    "link_etx": link.etx if link else float("inf"),
                }

                if not reachable:
                    self.parent_reachability[sensor_id] = {
                        "parent": parent_id,
                        "failed_since": now,
                        "triggered_repair": False,
                    }

            return results

    def trigger_local_repair(self, sensor_id: str, now: float) -> bool:
        """Trigger RPL local repair for a sensor that lost its parent."""
        with self._lock:
            rpl_engine = self.gateway.rpl_engine
            dodag_id = self.gateway.dodag_id

            if not dodag_id or dodag_id not in rpl_engine.dodag_configs:
                return False

            # Reset Trickle timer for DIO to solicit new parents
            if sensor_id in self.gateway._trickle_timers:
                if dodag_id in self.gateway._trickle_timers[sensor_id]:
                    timer = self.gateway._trickle_timers[sensor_id][dodag_id]
                    timer.on_inconsistent_heard(now)
                    self.repair_triggers += 1

                    # Mark repair as triggered
                    if sensor_id in self.parent_reachability:
                        self.parent_reachability[sensor_id]["triggered_repair"] = True

                    return True
            return False

    def check_repair_completion(self, now: float) -> list[str]:
        """Check if any pending repairs have completed."""
        with self._lock:
            completed = []
            rpl_engine = self.gateway.rpl_engine
            dodag_id = self.gateway.dodag_id

            if not dodag_id:
                return completed

            for sensor_id, info in list(self.parent_reachability.items()):
                if info.get("triggered_repair"):
                    state = rpl_engine.nodes_state.get(sensor_id)
                    if state and state.rank and state.rank.preferred_parent:
                        # Check if new parent is different and reachable
                        new_parent = state.rank.preferred_parent
                        link = self.gateway.topology.get_link_between(sensor_id, new_parent)
                        if link and link.available:
                            completed.append(sensor_id)
                            del self.parent_reachability[sensor_id]
                            self.repairs_completed += 1

            return completed

    def get_metrics(self, now: float) -> NetworkHealthMetrics:
        """Get network health metrics for the DODAG."""
        with self._lock:
            rpl_engine = self.gateway.rpl_engine
            dodag_id = self.gateway.dodag_id

            if not dodag_id or dodag_id not in rpl_engine.dodag_configs:
                return NetworkHealthMetrics(
                    dodag_id=dodag_id or "",
                    timestamp=now,
                    node_count=0,
                    reachable_nodes=0,
                    avg_rank=0,
                    avg_etx=0,
                    parent_changes=0,
                    dio_received=0,
                    dis_sent=0,
                    dao_sent=0,
                    routes_up=0,
                    routes_down=0,
                )

            sensors = self.gateway.device_manager.list_sensors()
            node_count = len(sensors) + 1  # +1 for gateway
            reachable = 0
            total_rank = 0
            total_etx = 0
            parent_changes = 0
            dio_received = 0
            dis_sent = 0
            dao_sent = 0
            routes_up = 0
            routes_down = 0

            for sensor_reg in sensors:
                sensor_id = sensor_reg.node_id
                state = rpl_engine.nodes_state.get(sensor_id)
                if state and state.rank:
                    if state.rank.rank < 0xFFFF:
                        reachable += 1
                        total_rank += state.rank.rank
                    if state.rank.preferred_parent:
                        parent_changes += state.parent_switch_count
                        link = self.gateway.topology.get_link_between(
                            sensor_id, state.rank.preferred_parent
                        )
                        if link:
                            total_etx += link.etx
                    dio_received += state.rank.dio_count if hasattr(state.rank, "dio_count") else 0
                    routes_up += 1

                    # Count downward routes
                    routes_down += len(state.routing_table)

            avg_rank = total_rank / reachable if reachable > 0 else 0
            avg_etx = total_etx / reachable if reachable > 0 else 0

            return NetworkHealthMetrics(
                dodag_id=dodag_id,
                timestamp=now,
                node_count=node_count,
                reachable_nodes=reachable,
                avg_rank=avg_rank,
                avg_etx=avg_etx,
                parent_changes=parent_changes,
                dio_received=dio_received,
                dis_sent=dis_sent,
                dao_sent=dao_sent,
                routes_up=routes_up,
                routes_down=routes_down,
            )

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "repair_triggers": self.repair_triggers,
                "repairs_completed": self.repairs_completed,
                "pending_repairs": len(self.parent_reachability),
                "last_check": self.last_check,
            }


class ForwardingManager:
    """Component 6: Routes sensor packets upward via RPL (compute_upward_route)."""

    def __init__(self, gateway: "Gateway") -> None:
        self.gateway = gateway
        self.forwarded_count = 0
        self.failed_count = 0
        self._lock = threading.Lock()

    def forward_to_gateway(self, sensor_id: str, reading: SensorReading) -> bool:
        """Forward sensor reading to gateway via RPL upward route."""
        with self._lock:
            rpl_engine = self.gateway.rpl_engine
            dodag_id = self.gateway.dodag_id

            if not dodag_id or dodag_id not in rpl_engine.dodag_configs:
                self.failed_count += 1
                return False

            # Compute upward route from sensor to gateway (root)
            route = rpl_engine.compute_upward_route(sensor_id, dodag_id)

            if not route or len(route) < 2:
                self.failed_count += 1
                return False

            # Verify route ends at gateway
            if route[-1] != self.gateway.gateway_id:
                self.failed_count += 1
                return False

            # Simulate forwarding along route
            # In a real implementation, this would send CoAP messages hop-by-hop
            # For simulation, we just verify the route exists and deliver
            self.forwarded_count += 1
            return True

    def get_upward_route(self, sensor_id: str) -> list[str]:
        """Get the upward route from sensor to gateway."""
        rpl_engine = self.gateway.rpl_engine
        dodag_id = self.gateway.dodag_id

        if not dodag_id or dodag_id not in rpl_engine.dodag_configs:
            return []

        return rpl_engine.compute_upward_route(sensor_id, dodag_id)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "forwarded": self.forwarded_count,
                "failed": self.failed_count,
            }


class Gateway:
    """Main Gateway class integrating all six components.

    The gateway acts as the DODAG root for its assigned sensors and provides
    resilient connectivity to the central server via MQTT.
    """

    def __init__(
        self,
        gateway_node: GatewayNode,
        topology: NetworkTopology,
        rpl_engine: RPLEngine,
        broker_host: str = "localhost",
        broker_port: int = 1883,
    ) -> None:
        self.gateway_node = gateway_node
        self.gateway_id = gateway_node.gateway_id
        self.topology = topology
        self.rpl_engine = rpl_engine
        self.dodag_id: str | None = None

        # Initialize six components
        self.sensor_ingestion = SensorIngestionComponent(self)
        self.device_manager = DeviceManager(self)
        self.local_storage = LocalStorageComponent(self)
        self.communication = CommunicationManager(
            self, broker_host, broker_port
        )
        self.network_monitor = NetworkMonitor(self)
        self.forwarding = ForwardingManager(self)

        # Trickle timers (managed by NetworkSimulator)
        self._trickle_timers: dict[str, dict[str, Any]] = {}

        # Optional federated-learning client (Stack 3).  This is deliberately
        # *not* one of the six telemetry components: it owns a separate MQTT
        # connection, a private dataset shard, and its own model.  Telemetry,
        # RPL, Trickle, and local-storage behaviour are unchanged when it is
        # absent.
        self.fl_client: Any = None

        # Dedicated FL state (never mixed with telemetry buffering).
        self.fl_storage = FLStorageComponent(self.gateway_id)

        # Gateway status
        self.status = GatewayStatus.ONLINE
        self._lock = threading.Lock()
        self._running = False
        self._monitor_thread: threading.Thread | None = None

        # Register assigned sensors
        self._register_assigned_sensors()

    def _register_assigned_sensors(self) -> None:
        """Register sensors assigned to this gateway."""
        sensors = self.topology.sensors_assigned_to(self.gateway_id)
        for sensor in sensors:
            self.device_manager.register_sensor(
                sensor.node_id,
                name=sensor.name,
                position=sensor.position,
            )

    def initialize_dodag(self, instance_id: int = 0, dodag_id: str | None = None) -> str:
        """Initialize DODAG for this gateway."""
        config = self.rpl_engine.initialize_dodag(
            self.gateway_id, instance_id, dodag_id
        )
        self.dodag_id = config.dodag_id
        return self.dodag_id

    def start(self, broker_host: str | None = None, broker_port: int | None = None) -> bool:
        """Start the gateway."""
        with self._lock:
            if self._running:
                return True

            if not self.dodag_id:
                self.initialize_dodag()

            # Update broker settings if provided
            if broker_host:
                self.communication.broker_host = broker_host
            if broker_port:
                self.communication.broker_port = broker_port

            # Connect to MQTT
            if not self.communication.connect():
                # Gateway can operate in offline mode
                pass

            self._running = True
            self.status = GatewayStatus.ONLINE
            return True

    def attach_fl_client(self, client: Any) -> None:
        """Attach a dedicated federated-learning client to this gateway."""
        self.fl_client = client

    def detach_fl_client(self) -> Any:
        """Detach the federated-learning client without stopping it."""
        client = self.fl_client
        self.fl_client = None
        return client

    def stop(self) -> None:
        """Stop the gateway and its optional FL client."""
        fl_client = self.fl_client
        if fl_client is not None:
            try:
                fl_client.stop()
            except Exception:  # pragma: no cover - FL must not break telemetry
                pass
            self.fl_client = None
        with self._lock:
            if not self._running:
                return

            self._running = False
            self.status = GatewayStatus.OFFLINE
            self.communication.disconnect()

    def receive_sensor_telemetry(
        self, sensor_id: str, reading: SensorReading, route: list[str]
    ) -> bool:
        """Receive telemetry from sensor (called by simulation engine)."""
        return self.sensor_ingestion.receive_telemetry(sensor_id, reading, route)

    def process_outbound_telemetry(self) -> int:
        """Process pending telemetry for MQTT publishing."""
        pending = self.local_storage.get_pending(limit=100)
        published = 0

        for entry in pending:
            if self.communication.publish_telemetry(entry.sensor_id, entry.reading):
                self.local_storage.mark_mqtt_published(entry.sensor_id, entry.timestamp)
                published += 1

        return published

    def publish_status(self) -> bool:
        """Publish gateway status."""
        return self.communication.publish_status(self.status.value)

    def publish_health(self) -> bool:
        """Publish gateway health metrics."""
        metrics = self.network_monitor.get_metrics(time.time())
        return self.communication.publish_health(metrics.__dict__)

    def check_network_health(self, now: float) -> dict[str, Any]:
        """Run network health checks and trigger repairs if needed."""
        reachability = self.network_monitor.check_parent_reachability(now)

        # Trigger repairs for unreachable parents
        for sensor_id, info in reachability.items():
            if not info["reachable"] and not info.get("triggered_repair", False):
                self.network_monitor.trigger_local_repair(sensor_id, now)

        # Check repair completion
        completed = self.network_monitor.check_repair_completion(now)

        return {
            "reachability": reachability,
            "repairs_completed": completed,
            "metrics": self.network_monitor.get_metrics(now).__dict__,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive gateway statistics."""
        with self._lock:
            return {
                "gateway_id": self.gateway_id,
                "dodag_id": self.dodag_id,
                "status": self.status.value,
                "running": self._running,
                "sensor_ingestion": self.sensor_ingestion.get_stats(),
                "device_manager": self.device_manager.get_stats(),
                "local_storage": self.local_storage.get_stats(),
                "communication": self.communication.get_stats(),
                "network_monitor": self.network_monitor.get_stats(),
                "forwarding": self.forwarding.get_stats(),
                "fl_storage": self.fl_storage.get_stats(),
            }

    def to_dict(self) -> dict[str, Any]:
        """Serialize gateway for API."""
        return {
            "node_type": "gateway",
            "gateway_id": self.gateway_id,
            "name": self.gateway_node.name,
            "position": self.gateway_node.position.to_dict() if self.gateway_node.position else None,
            "available": self.gateway_node.available,
            "dodag_id": self.dodag_id,
            "status": self.status.value,
            "transmission_range_m": self.gateway_node.transmission_range_m,
            "storage_capacity_mb": self.gateway_node.local_storage.capacity_mb,
            "storage_used_mb": self.gateway_node.local_storage.used_mb,
            "connected_sensor_count": self.gateway_node.connected_sensor_count,
            "fl_client": (
                self.fl_client.snapshot() if self.fl_client is not None else None
            ),
            "stats": self.get_stats(),
        }


def create_gateway(
    gateway_node: GatewayNode,
    topology: NetworkTopology,
    rpl_engine: RPLEngine,
    broker_host: str = "localhost",
    broker_port: int = 1883,
) -> Gateway:
    """Factory function to create a Gateway."""
    return Gateway(gateway_node, topology, rpl_engine, broker_host, broker_port)