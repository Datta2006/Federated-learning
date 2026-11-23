"""Monitoring Component for Edge Inference (Stack 4).

Provides system and application-level metrics for the gateway:
- CPU, memory, battery, network
- MQTT connection status and message rates
- Storage usage
- Model version and inference latency
- SNMPv3 abstraction for standard monitoring
"""

from __future__ import annotations

import logging
import platform
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import psutil

LOGGER = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """System-level metrics snapshot."""

    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_free_gb: float
    disk_total_gb: float
    battery_percent: float | None
    battery_charging: bool | None
    uptime_seconds: float
    load_average: tuple[float, float, float] | None
    timestamp: str


@dataclass
class NetworkMetrics:
    """Network interface metrics."""

    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errors_in: int
    errors_out: int
    drop_in: int
    drop_out: int
    interfaces: dict[str, dict[str, int]]
    timestamp: str


@dataclass
class MQTTMetrics:
    """MQTT connection and message metrics."""

    connected: bool
    broker_host: str
    broker_port: int
    client_id: str
    messages_published: int
    messages_received: int
    publish_errors: int
    receive_errors: int
    last_publish_at: float | None
    last_receive_at: float | None
    reconnect_count: int
    timestamp: str


@dataclass
class StorageMetrics:
    """Local storage metrics."""

    total_files: int
    total_size_bytes: int
    telemetry_files: int
    telemetry_size_bytes: int
    model_files: int
    model_size_bytes: int
    fl_files: int
    fl_size_bytes: int
    oldest_file_age_seconds: float | None
    newest_file_age_seconds: float | None
    timestamp: str


@dataclass
class InferenceMetrics:
    """Inference performance metrics."""

    inference_count: int
    inference_errors: int
    avg_inference_ms: float
    last_inference_ms: float | None
    last_inference_at: float | None
    model_version: int | None
    model_loaded: bool
    timestamp: str


@dataclass
class GatewayMetrics:
    """Complete gateway metrics snapshot."""

    system: SystemMetrics
    network: NetworkMetrics
    mqtt: MQTTMetrics
    storage: StorageMetrics
    inference: InferenceMetrics
    gateway_id: str
    timestamp: str


class MonitoringComponent:
    """Monitors gateway health, performance, and operational metrics.

    - System metrics (CPU, memory, disk, battery) via psutil
    - Network interface statistics
    - MQTT connection and message rates
    - Local storage usage breakdown
    - Inference performance tracking
    - SNMPv3-compatible metric export
    """

    def __init__(
        self,
        gateway_id: str,
        mqtt_client: Any = None,
        local_storage: Any = None,
        inference_component: Any = None,
        model_deployment: Any = None,
        collection_interval_seconds: int = 30,
        history_limit: int = 1000,
    ) -> None:
        self.gateway_id = gateway_id
        self.mqtt_client = mqtt_client
        self.local_storage = local_storage
        self.inference_component = inference_component
        self.model_deployment = model_deployment
        self.collection_interval = collection_interval_seconds
        self.history_limit = history_limit

        self._lock = threading.RLock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._collection_count = 0
        self._collection_errors = 0
        self._last_collection_at: float | None = None
        self._last_metrics: GatewayMetrics | None = None
        self._history: list[GatewayMetrics] = []

        # MQTT counters (updated externally by communication manager)
        self._mqtt_published = 0
        self._mqtt_received = 0
        self._mqtt_publish_errors = 0
        self._mqtt_receive_errors = 0
        self._mqtt_last_publish_at: float | None = None
        self._mqtt_last_receive_at: float | None = None
        self._mqtt_reconnect_count = 0

        # Inference counters (updated externally by inference component)
        self._inference_count = 0
        self._inference_errors = 0
        self._total_inference_ms = 0.0
        self._last_inference_ms: float | None = None
        self._last_inference_at: float | None = None

        # SNMPv3 configuration
        self._snmp_enabled = False
        self._snmp_port = 161
        self._snmp_user = "gateway_monitor"
        self._snmp_auth_proto = "SHA"
        self._snmp_priv_proto = "AES"

    # -------------------------------------------------------------------- SNMP
    def configure_snmp(
        self,
        enabled: bool = True,
        port: int = 161,
        user: str = "gateway_monitor",
        auth_proto: str = "SHA",
        priv_proto: str = "AES",
    ) -> dict[str, Any]:
        """Configure SNMPv3 settings."""
        with self._lock:
            self._snmp_enabled = enabled
            self._snmp_port = port
            self._snmp_user = user
            self._snmp_auth_proto = auth_proto
            self._snmp_priv_proto = priv_proto
        return self.get_snmp_config()

    def get_snmp_config(self) -> dict[str, Any]:
        """Get current SNMPv3 configuration."""
        with self._lock:
            return {
                "enabled": self._snmp_enabled,
                "port": self._snmp_port,
                "user": self._snmp_user,
                "auth_protocol": self._snmp_auth_proto,
                "priv_protocol": self._snmp_priv_proto,
            }

    def get_snmp_metrics(self) -> dict[str, Any]:
        """Get metrics in SNMP-compatible format (OID-style mapping)."""
        metrics = self.collect()
        if metrics is None:
            return {}

        # Map to pseudo-OIDs for SNMPv3 abstraction
        return {
            "1.3.6.1.4.1.99999.1.1": metrics.system.cpu_percent,  # CPU
            "1.3.6.1.4.1.99999.1.2": metrics.system.memory_percent,  # Memory
            "1.3.6.1.4.1.99999.1.3": metrics.system.disk_percent,  # Disk
            "1.3.6.1.4.1.99999.1.4": metrics.system.battery_percent or 0,  # Battery
            "1.3.6.1.4.1.99999.2.1": metrics.mqtt.messages_published,  # MQTT pub
            "1.3.6.1.4.1.99999.2.2": metrics.mqtt.messages_received,  # MQTT recv
            "1.3.6.1.4.1.99999.2.3": 1 if metrics.mqtt.connected else 0,  # MQTT connected
            "1.3.6.1.4.1.99999.3.1": metrics.inference.inference_count,  # Inference count
            "1.3.6.1.4.1.99999.3.2": metrics.inference.avg_inference_ms,  # Avg latency
            "1.3.6.1.4.1.99999.3.3": metrics.inference.model_version or 0,  # Model version
            "1.3.6.1.4.1.99999.4.1": metrics.storage.total_size_bytes,  # Storage total
            "1.3.6.1.4.1.99999.4.2": metrics.storage.total_files,  # Storage files
        }

    # ------------------------------------------------------------------ Public API
    def start(self) -> dict[str, Any]:
        """Start background metrics collection."""
        with self._lock:
            if self._running:
                return {"status": "already_running"}
            self._running = True
            self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._collection_loop,
            name=f"monitor-{self.gateway_id}",
            daemon=True,
        )
        self._thread.start()
        return {"status": "started", "interval_seconds": self.collection_interval}

    def stop(self) -> dict[str, Any]:
        """Stop background metrics collection."""
        with self._lock:
            if not self._running:
                return {"status": "not_running"}
            self._running = False
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        return {"status": "stopped", "collections": self._collection_count}

    def collect(self) -> GatewayMetrics | None:
        """Collect a single metrics snapshot."""
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        try:
            system = self._collect_system(timestamp)
            network = self._collect_network(timestamp)
            mqtt = self._collect_mqtt(timestamp)
            storage = self._collect_storage(timestamp)
            inference = self._collect_inference(timestamp)

            metrics = GatewayMetrics(
                system=system,
                network=network,
                mqtt=mqtt,
                storage=storage,
                inference=inference,
                gateway_id=self.gateway_id,
                timestamp=timestamp,
            )

            with self._lock:
                self._collection_count += 1
                self._last_collection_at = time.time()
                self._last_metrics = metrics
                self._history.append(metrics)
                if len(self._history) > self.history_limit:
                    self._history.pop(0)

            return metrics
        except Exception:
            LOGGER.exception("Metrics collection failed")
            with self._lock:
                self._collection_errors += 1
            return None

    def record_mqtt_publish(self, success: bool = True) -> None:
        """Record an MQTT publish event (called by CommunicationManager)."""
        with self._lock:
            if success:
                self._mqtt_published += 1
                self._mqtt_last_publish_at = time.time()
            else:
                self._mqtt_publish_errors += 1

    def record_mqtt_receive(self, success: bool = True) -> None:
        """Record an MQTT receive event (called by CommunicationManager)."""
        with self._lock:
            if success:
                self._mqtt_received += 1
                self._mqtt_last_receive_at = time.time()
            else:
                self._mqtt_receive_errors += 1

    def record_mqtt_reconnect(self) -> None:
        """Record an MQTT reconnection event."""
        with self._lock:
            self._mqtt_reconnect_count += 1

    def record_inference(self, inference_ms: float, success: bool = True) -> None:
        """Record an inference event (called by InferenceComponent)."""
        with self._lock:
            if success:
                self._inference_count += 1
                self._total_inference_ms += inference_ms
                self._last_inference_ms = inference_ms
                self._last_inference_at = time.time()
            else:
                self._inference_errors += 1

    def get_stats(self) -> dict[str, Any]:
        """Get component statistics."""
        with self._lock:
            avg_ms = (
                self._total_inference_ms / self._inference_count
                if self._inference_count > 0
                else 0.0
            )
            return {
                "gateway_id": self.gateway_id,
                "running": self._running,
                "collection_interval_seconds": self.collection_interval,
                "collection_count": self._collection_count,
                "collection_errors": self._collection_errors,
                "last_collection_at": self._last_collection_at,
                "mqtt": {
                    "published": self._mqtt_published,
                    "received": self._mqtt_received,
                    "publish_errors": self._mqtt_publish_errors,
                    "receive_errors": self._mqtt_receive_errors,
                    "last_publish_at": self._mqtt_last_publish_at,
                    "last_receive_at": self._mqtt_last_receive_at,
                    "reconnect_count": self._mqtt_reconnect_count,
                },
                "inference": {
                    "count": self._inference_count,
                    "errors": self._inference_errors,
                    "avg_ms": avg_ms,
                    "last_ms": self._last_inference_ms,
                    "last_at": self._last_inference_at,
                },
                "snmp": self.get_snmp_config(),
            }

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for monitoring."""
        with self._lock:
            metrics = self._last_metrics
            return {
                "component": "MonitoringComponent",
                "gateway_id": self.gateway_id,
                "stats": self.get_stats(),
                "latest_metrics": metrics.__dict__ if metrics else None,
                "history_length": len(self._history),
            }

    def get_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent metrics history for dashboard."""
        with self._lock:
            return [m.__dict__ for m in self._history[-limit:]]

    # -------------------------------------------------------------------- Internal
    def _collection_loop(self) -> None:
        """Background metrics collection loop."""
        while not self._stop_event.is_set():
            self.collect()
            self._stop_event.wait(self.collection_interval)

    def _collect_system(self, timestamp: str) -> SystemMetrics:
        """Collect system-level metrics."""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # Memory
        mem = psutil.virtual_memory()
        memory_percent = mem.percent
        memory_available_mb = mem.available / (1024 * 1024)
        memory_total_mb = mem.total / (1024 * 1024)

        # Disk
        disk = psutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100
        disk_free_gb = disk.free / (1024 * 1024 * 1024)
        disk_total_gb = disk.total / (1024 * 1024 * 1024)

        # Battery
        battery_percent = None
        battery_charging = None
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_percent = battery.percent
                battery_charging = battery.power_plugged
        except Exception:
            pass

        # Uptime
        uptime_seconds = time.time() - psutil.boot_time()

        # Load average (Unix only)
        load_average = None
        try:
            load_average = psutil.getloadavg()
        except Exception:
            pass

        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_available_mb=memory_available_mb,
            memory_total_mb=memory_total_mb,
            disk_percent=disk_percent,
            disk_free_gb=disk_free_gb,
            disk_total_gb=disk_total_gb,
            battery_percent=battery_percent,
            battery_charging=battery_charging,
            uptime_seconds=uptime_seconds,
            load_average=load_average,
            timestamp=timestamp,
        )

    def _collect_network(self, timestamp: str) -> NetworkMetrics:
        """Collect network interface metrics."""
        net_io = psutil.net_io_counters(pernic=True)
        interfaces = {}
        total_sent = 0
        total_recv = 0
        total_psent = 0
        total_precv = 0
        total_ein = 0
        total_eout = 0
        total_din = 0
        total_dout = 0

        for iface, stats in net_io.items():
            interfaces[iface] = {
                "bytes_sent": stats.bytes_sent,
                "bytes_recv": stats.bytes_recv,
                "packets_sent": stats.packets_sent,
                "packets_recv": stats.packets_recv,
                "errin": stats.errin,
                "errout": stats.errout,
                "dropin": stats.dropin,
                "dropout": stats.dropout,
            }
            total_sent += stats.bytes_sent
            total_recv += stats.bytes_recv
            total_psent += stats.packets_sent
            total_precv += stats.packets_recv
            total_ein += stats.errin
            total_eout += stats.errout
            total_din += stats.dropin
            total_dout += stats.dropout

        return NetworkMetrics(
            bytes_sent=total_sent,
            bytes_recv=total_recv,
            packets_sent=total_psent,
            packets_recv=total_precv,
            errors_in=total_ein,
            errors_out=total_eout,
            drop_in=total_din,
            drop_out=total_dout,
            interfaces=interfaces,
            timestamp=timestamp,
        )

    def _collect_mqtt(self, timestamp: str) -> MQTTMetrics:
        """Collect MQTT metrics."""
        connected = False
        broker_host = "unknown"
        broker_port = 1883
        client_id = f"gateway-{self.gateway_id}"

        if self.mqtt_client is not None:
            try:
                connected = self.mqtt_client.is_connected()
                if hasattr(self.mqtt_client, "_host"):
                    broker_host = self.mqtt_client._host
                if hasattr(self.mqtt_client, "_port"):
                    broker_port = self.mqtt_client._port
                if hasattr(self.mqtt_client, "_client_id"):
                    client_id = self.mqtt_client._client_id
            except Exception:
                pass

        return MQTTMetrics(
            connected=connected,
            broker_host=broker_host,
            broker_port=broker_port,
            client_id=client_id,
            messages_published=self._mqtt_published,
            messages_received=self._mqtt_received,
            publish_errors=self._mqtt_publish_errors,
            receive_errors=self._mqtt_receive_errors,
            last_publish_at=self._mqtt_last_publish_at,
            last_receive_at=self._mqtt_last_receive_at,
            reconnect_count=self._mqtt_reconnect_count,
            timestamp=timestamp,
        )

    def _collect_storage(self, timestamp: str) -> StorageMetrics:
        """Collect local storage metrics."""
        total_files = 0
        total_size = 0
        telemetry_files = 0
        telemetry_size = 0
        model_files = 0
        model_size = 0
        fl_files = 0
        fl_size = 0
        oldest_age: float | None = None
        newest_age: float | None = None
        now = time.time()

        if self.local_storage is not None:
            try:
                all_files = self.local_storage.list("")
                for f in all_files:
                    try:
                        stat = self.local_storage.stat(f)
                        size = stat.get("size", 0) if isinstance(stat, dict) else 0
                        mtime = stat.get("mtime", now) if isinstance(stat, dict) else now
                        age = now - mtime

                        total_files += 1
                        total_size += size

                        if f.startswith("telemetry/"):
                            telemetry_files += 1
                            telemetry_size += size
                        elif f.startswith("models/"):
                            model_files += 1
                            model_size += size
                        elif f.startswith("fl/"):
                            fl_files += 1
                            fl_size += size

                        if oldest_age is None or age > oldest_age:
                            oldest_age = age
                        if newest_age is None or age < newest_age:
                            newest_age = age
                    except Exception:
                        continue
            except Exception:
                pass

        return StorageMetrics(
            total_files=total_files,
            total_size_bytes=total_size,
            telemetry_files=telemetry_files,
            telemetry_size_bytes=telemetry_size,
            model_files=model_files,
            model_size_bytes=model_size,
            fl_files=fl_files,
            fl_size_bytes=fl_size,
            oldest_file_age_seconds=oldest_age,
            newest_file_age_seconds=newest_age,
            timestamp=timestamp,
        )

    def _collect_inference(self, timestamp: str) -> InferenceMetrics:
        """Collect inference metrics."""
        model_version = None
        model_loaded = False

        if self.inference_component is not None:
            try:
                stats = self.inference_component.get_stats()
                model_version = stats.get("model_version")
                model_loaded = stats.get("model_loaded", False)
            except Exception:
                pass

        avg_ms = (
            self._total_inference_ms / self._inference_count
            if self._inference_count > 0
            else 0.0
        )

        return InferenceMetrics(
            inference_count=self._inference_count,
            inference_errors=self._inference_errors,
            avg_inference_ms=avg_ms,
            last_inference_ms=self._last_inference_ms,
            last_inference_at=self._last_inference_at,
            model_version=model_version,
            model_loaded=model_loaded,
            timestamp=timestamp,
        )


__all__ = [
    "MonitoringComponent",
    "SystemMetrics",
    "NetworkMetrics",
    "MQTTMetrics",
    "StorageMetrics",
    "InferenceMetrics",
    "GatewayMetrics",
]