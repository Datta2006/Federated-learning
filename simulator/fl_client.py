"""Gateway-hosted federated-learning clients (Approach 2).

Each simulator gateway can act as an independent FL client.  This module is a
lifecycle wrapper around the existing :class:`node.fl_node.FederatedNode`: it
does not reimplement the worker protocol, MQTT topics, chunked delivery, FedAvg
validation, or the CNN-RNN model.  It adds only:

* a stable, collision-safe gateway -> worker identity,
* a disjoint, reproducible gateway-local dataset partition,
* dedicated FL storage (separate from telemetry buffering),
* single-flight lifecycle (one training thread per gateway).

Training runs on the node's own worker thread with its own MQTT client, so the
simulator's telemetry loop and ``LocalStorageComponent`` are never touched by
local training.  ``stop()`` is an intentional dropout: the client disconnects,
the coordinator's retained registry expires it, and round deadline /
partial-participation rules decide the outcome.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from common.config import load_config
from common.worker_protocol import (
    worker_register_topic,
    worker_state_topic,
)
from simulator.fl_identity import GatewayIdentity, GatewayIdentityRegistry

LOGGER = logging.getLogger(__name__)

# Process-wide so two gateways that sanitise to the same slug still get distinct
# worker ids even if they are created by different clients.
_DEFAULT_IDENTITIES = GatewayIdentityRegistry()


class FLClientError(RuntimeError):
    """Raised for invalid or duplicate gateway FL client operations."""


class FederatedLearningClient:
    """One gateway's independent FL client lifecycle and read-only snapshot."""

    def __init__(
        self,
        gateway_id: str,
        *,
        config_path: str | None = None,
        host: str | None = None,
        port: int | None = None,
        seed: int | None = None,
        window_hours: int | None = None,
        shard_index: int = 0,
        shard_count: int = 1,
        dummy: bool = False,
        dummy_value: float = 1.0,
        dummy_samples: int = 100,
        dummy_count: int = 9025,
        upload_delay: float = 0.0,
        ack_timeout: float = 30.0,
        run_seconds: float | None = None,
        fl_storage: Any = None,
        identity_registry: GatewayIdentityRegistry | None = None,
        node_factory: Callable[..., Any] | None = None,
        worker_id: str | None = None,
    ) -> None:
        if shard_count < 1:
            raise ValueError("shard_count must be at least 1")
        if not 0 <= int(shard_index) < int(shard_count):
            raise ValueError(
                f"shard_index {shard_index} is outside 0..{int(shard_count) - 1}"
            )
        self.gateway_id = str(gateway_id)
        self.shard_index = int(shard_index)
        self.shard_count = int(shard_count)
        self.config_path = config_path
        self.config = load_config(config_path)
        mqtt_cfg = self.config.get("mqtt", {})
        self.base_topic = str(mqtt_cfg.get("base_topic", "aq"))
        self.host = str(host or mqtt_cfg.get("host", "127.0.0.1"))
        self.port = int(port or mqtt_cfg.get("port", 1883))
        self.seed = seed
        self.window_hours = int(
            window_hours
            if window_hours is not None
            else self.config.get("window_hours", 24)
        )
        self.dummy = bool(dummy)
        self.dummy_value = float(dummy_value)
        self.dummy_samples = int(dummy_samples)
        self.dummy_count = int(dummy_count)
        self.upload_delay = float(upload_delay)
        self.ack_timeout = float(ack_timeout)
        self.run_seconds = run_seconds
        self.fl_storage = fl_storage
        self.node_factory = node_factory or _default_node_factory

        registry = identity_registry or _DEFAULT_IDENTITIES
        identity: GatewayIdentity = registry.assign(self.gateway_id)
        self.worker_id = str(worker_id or identity.worker_id)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._node: Any = None
        self._state = "idle"
        self._last_error: str | None = None
        self._prepared = False
        self._starts = 0

    # ---------------------------------------------------------------- prepare
    def prepare(self) -> dict[str, Any]:
        """Load the gateway-local dataset and build its model (idempotent)."""
        with self._lock:
            if self._prepared and self._node is not None:
                return self._snapshot_locked()
            node = self._node or self._build_node()
            self._node = node
            # Reuse the node's own loader so preprocessing, scaler, model
            # architecture, and partition selection are exactly the same code
            # path the standalone worker uses.  Test seams may provide a node
            # without a loader; those are already "prepared".
            loader = getattr(node, "_load_training_state", None)
            if callable(loader):
                loader()
            if self.dummy:
                node.n_samples = self.dummy_samples
                node.n_val = self.dummy_samples
            self._prepared = True
            self._state = "available"
            snapshot = self._snapshot_locked()
        if self.fl_storage is not None:
            try:
                self.fl_storage.write_state(
                    worker_id=self.worker_id,
                    gateway_index=self.shard_index,
                    gateway_count=self.shard_count,
                    window_hours=self.window_hours,
                    dummy=self.dummy,
                    client_state="available",
                )
            except Exception:  # pragma: no cover
                LOGGER.exception("could not persist gateway FL prepare state")
        return snapshot

    @property
    def prepared(self) -> dict[str, Any] | None:
        node = self._node
        return None if node is None else getattr(node, "prepared", None)

    # ------------------------------------------------------------- lifecycle
    @property
    def running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self) -> dict[str, Any]:
        """Start the single local-training thread for this gateway."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise FLClientError(
                    f"gateway {self.gateway_id!r} already has a running FL client"
                )
        if not self._prepared:
            self.prepare()
        with self._lock:
            self._stop_event = threading.Event()
            node = self._node
            assert node is not None
            try:
                node._stop = self._stop_event
            except AttributeError:  # pragma: no cover - fake node seam
                pass
            self._thread = threading.Thread(
                target=self._run,
                name=f"fl-{self.worker_id}",
                daemon=True,
            )
            self._state = "running"
            self._starts += 1
            self._thread.start()
        return self.snapshot()

    def _run(self) -> None:
        try:
            with self._lock:
                self._state = "running"
            assert self._node is not None
            self._node.run()
            with self._lock:
                if self._state != "error":
                    self._state = "offline"
        except Exception as exc:  # pragma: no cover - long-lived safety net
            LOGGER.exception("gateway FL client %s failed", self.worker_id)
            with self._lock:
                self._state = "error"
                self._last_error = str(exc)
        finally:
            if self.fl_storage is not None:
                try:
                    self.fl_storage.write_state(
                        worker_id=self.worker_id,
                        client_state=self._state,
                        last_error=self._last_error,
                    )
                except Exception:  # pragma: no cover
                    LOGGER.exception("could not persist FL client stop state")

    def stop(self, timeout: float = 10.0) -> dict[str, Any]:
        """Intentional dropout: finish the node loop and disconnect."""
        with self._lock:
            thread = self._thread
            node = self._node
            self._stop_event.set()
            if node is not None:
                try:
                    node._stop.set()
                except AttributeError:  # pragma: no cover
                    pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        with self._lock:
            if thread is None or not thread.is_alive():
                self._thread = None
                if self._state != "error":
                    self._state = "offline"
            return self._snapshot_locked()

    def simulate_dropout(self, timeout: float = 10.0) -> dict[str, Any]:
        return self.stop(timeout=timeout)

    # --------------------------------------------------------------- snapshot
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        node = self._node
        partition_info = getattr(node, "_partition_info", None) if node else None
        partition = (
            dict(partition_info.get("partition") or {})
            if isinstance(partition_info, dict)
            else {}
        )
        if isinstance(partition_info, dict):
            partition.update(
                {
                    "years": list(partition_info.get("years") or []),
                    "shard_indices": list(
                        partition_info.get("shard_indices") or []
                    ),
                    "n_samples": partition_info.get("n_samples"),
                    "n_val": partition_info.get("n_val"),
                    "source_rows": partition_info.get("source_rows"),
                }
            )
        if self.dummy and not partition:
            partition = {
                "start_row": 0,
                "end_row": self.dummy_samples,
                "dummy": True,
            }
        n_samples = (
            getattr(node, "n_samples", self.dummy_samples)
            if node is not None
            else (self.dummy_samples if self.dummy else 0)
        )
        n_val = (
            getattr(node, "n_val", self.dummy_samples)
            if node is not None
            else (self.dummy_samples if self.dummy else 0)
        )
        parameters = 0
        if self.dummy:
            parameters = self.dummy_count
        elif node is not None and getattr(node, "model", None) is not None:
            try:
                parameters = int(node.model.count_params())
            except Exception:  # pragma: no cover
                parameters = 0
        prepared_data = getattr(node, "prepared", None) if node is not None else None
        n_features = int(prepared_data["n_features"]) if prepared_data else 0
        year = getattr(node, "year", None) if node is not None else None
        years = list(getattr(node, "years", []) or ([year] if year else []))
        running = self._thread is not None and self._thread.is_alive()
        snapshot = {
            "gateway_id": self.gateway_id,
            "worker_id": self.worker_id,
            "gateway_index": self.shard_index,
            "gateway_count": self.shard_count,
            "shard_index": self.shard_index,
            "shard_count": self.shard_count,
            "running": running,
            "state": self._state,
            "worker_state": getattr(node, "_worker_state", None)
            if node is not None
            else None,
            "current_round": getattr(node, "_round_number", None)
            if node is not None
            else None,
            "training_active": bool(running and self._state == "running"),
            "prepared": self._prepared,
            "dummy": self.dummy,
            "dataset": getattr(node, "_dataset_label", "unknown")
            if node is not None
            else "unknown",
            "year": year,
            "years": years,
            "n_samples": int(n_samples),
            "n_val": int(n_val),
            "n_features": n_features,
            "parameters": parameters,
            "partition": partition,
            "mqtt_client_id": f"gateway-fl-{self.gateway_id}",
            "topics": {
                "register": worker_register_topic(self.base_topic, self.worker_id),
                "state": worker_state_topic(self.base_topic, self.worker_id),
            },
            "storage": {
                "directory": str(self.fl_storage.directory)
            } if self.fl_storage is not None else None,
            "last_error": self._last_error,
            "starts": self._starts,
        }
        return snapshot

    # --------------------------------------------------------------- factory
    def _build_node(self) -> Any:
        return self.node_factory(
            config_path=self.config_path,
            node_id=self.worker_id,
            host=self.host,
            port=self.port,
            seed=self.seed,
            window_hours=self.window_hours,
            dummy=self.dummy,
            dummy_value=self.dummy_value,
            dummy_samples=self.dummy_samples,
            dummy_count=self.dummy_count,
            upload_delay=self.upload_delay,
            ack_timeout=self.ack_timeout,
            run_seconds=self.run_seconds,
            allow_dynamic=True,
            simulation=not self.dummy,
            gateway_index=self.shard_index,
            gateway_count=self.shard_count,
            stop_event=self._stop_event,
            fl_storage=self.fl_storage,
        )


def _default_node_factory(**kwargs: Any) -> Any:
    # Imported lazily so importing the simulator does not pull TensorFlow or
    # build an FL node until a gateway actually joins federated training.
    from node.fl_node import FederatedNode

    return FederatedNode(**kwargs)


class GatewayFLFleet:
    """Deterministically assign partitions/ids and own gateway clients.

    The engine uses this as the single owner of all gateway FL clients so a
    gateway restart receives the same partition index and worker id.
    """

    def __init__(
        self,
        *,
        config_path: str | None = None,
        gateway_count: int = 3,
        identity_registry: GatewayIdentityRegistry | None = None,
        node_factory: Callable[..., Any] | None = None,
    ) -> None:
        if gateway_count < 1:
            raise ValueError("gateway_count must be at least 1")
        self.config_path = config_path
        self.gateway_count = int(gateway_count)
        self.identity_registry = identity_registry or GatewayIdentityRegistry()
        self.node_factory = node_factory
        self._lock = threading.RLock()
        self._clients: dict[str, FederatedLearningClient] = {}
        self._indices: dict[str, int] = {}

    def _assign_index(self, gateway_id: str) -> int:
        with self._lock:
            existing = self._indices.get(gateway_id)
            if existing is not None:
                return existing
            used = set(self._indices.values())
            for index in range(self.gateway_count):
                if index not in used:
                    self._indices[gateway_id] = index
                    return index
            raise FLClientError(
                f"no free gateway partition; fleet is sized for {self.gateway_count}"
            )

    def start(
        self,
        gateway_id: str,
        *,
        fl_storage: Any = None,
        prepare: bool = False,
        **overrides: Any,
    ) -> FederatedLearningClient:
        with self._lock:
            client = self._clients.get(gateway_id)
            if client is not None and client.running:
                raise FLClientError(
                    f"gateway {gateway_id!r} already has a running FL client"
                )
            index = self._assign_index(gateway_id)
            options = {
                "config_path": self.config_path,
                "shard_index": index,
                "shard_count": self.gateway_count,
                "fl_storage": fl_storage,
                "identity_registry": self.identity_registry,
                "node_factory": self.node_factory,
            }
            options.update(overrides)
            # Look the class up at call time so tests can monkeypatch the seam.
            client = FederatedLearningClient(gateway_id, **options)
            if prepare:
                client.prepare()
            client.start()
            self._clients[gateway_id] = client
            return client

    def stop(self, gateway_id: str, *, timeout: float = 10.0) -> dict[str, Any] | None:
        with self._lock:
            client = self._clients.get(gateway_id)
        if client is None:
            return None
        result = client.stop(timeout=timeout)
        with self._lock:
            self._clients.pop(gateway_id, None)
        return result

    def stop_all(self, *, timeout: float = 10.0) -> dict[str, dict[str, Any] | None]:
        with self._lock:
            clients = dict(self._clients)
        return {
            gateway_id: client.stop(timeout=timeout)
            for gateway_id, client in clients.items()
        }

    def client(self, gateway_id: str) -> FederatedLearningClient | None:
        with self._lock:
            return self._clients.get(gateway_id)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            clients = dict(self._clients)
        return {
            "gateway_count": self.gateway_count,
            "partitions": dict(self._indices),
            "clients": {
                gateway_id: client.snapshot()
                for gateway_id, client in sorted(clients.items())
            },
        }


__all__ = [
    "FLClientError",
    "FederatedLearningClient",
    "GatewayFLFleet",
]
