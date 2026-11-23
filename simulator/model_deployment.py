"""Model Deployment Component for Edge Inference (Stack 4).

Receives global models via MQTT (retained messages), validates them, stores
checkpoints locally, and provides the active model to the InferenceComponent.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from common.model import unflatten_weights

LOGGER = logging.getLogger(__name__)


@dataclass
class ModelCheckpoint:
    """A stored model checkpoint with metadata."""

    version: int
    weights: list[np.ndarray]
    metrics: dict[str, float]
    received_at: float
    source_topic: str
    parameters: int
    architecture_hash: str


class ModelDeploymentComponent:
    """Manages model deployment lifecycle on the gateway.

    - Subscribes to MQTT model topics (retained messages)
    - Validates model architecture compatibility
    - Stores checkpoints to local storage
    - Provides active model for inference
    - Handles model versioning and rollback
    """

    def __init__(
        self,
        gateway_id: str,
        base_topic: str = "aq",
        mqtt_client: Any = None,
        local_storage: Any = None,
        expected_architecture_hash: str | None = None,
        max_checkpoints: int = 5,
        validation_fn: Callable[[list[np.ndarray]], bool] | None = None,
    ) -> None:
        self.gateway_id = gateway_id
        self.base_topic = base_topic
        self.mqtt_client = mqtt_client
        self.local_storage = local_storage
        self.expected_architecture_hash = expected_architecture_hash
        self.max_checkpoints = max_checkpoints
        self.validation_fn = validation_fn

        self._lock = threading.RLock()
        self._checkpoints: dict[int, ModelCheckpoint] = {}
        self._active_version: int | None = None
        self._active_weights: list[np.ndarray] | None = None
        self._active_architecture_hash: str | None = None
        self._subscribed = False
        self._last_model_received_at: float | None = None
        self._model_receive_count = 0
        self._validation_failures = 0

    @property
    def active_version(self) -> int | None:
        with self._lock:
            return self._active_version

    @property
    def active_weights(self) -> list[np.ndarray] | None:
        with self._lock:
            return self._active_weights

    @property
    def has_model(self) -> bool:
        with self._lock:
            return self._active_weights is not None

    def start(self) -> dict[str, Any]:
        """Start MQTT subscription for model updates."""
        with self._lock:
            if self._subscribed:
                return {"status": "already_subscribed"}
            self._subscribed = True
        self._subscribe_mqtt()
        return {"status": "subscribed", "topic": self._model_topic()}

    def stop(self) -> dict[str, Any]:
        """Stop MQTT subscription."""
        with self._lock:
            self._subscribed = False
        self._unsubscribe_mqtt()
        return {"status": "unsubscribed"}

    def _model_topic(self) -> str:
        return f"{self.base_topic}/model/global"

    def _subscribe_mqtt(self) -> None:
        if self.mqtt_client is None:
            LOGGER.warning("No MQTT client available for model deployment")
            return
        try:
            self.mqtt_client.subscribe(self._model_topic(), qos=1)
            self.mqtt_client.message_callback_add(
                self._model_topic(), self._on_model_message
            )
            LOGGER.info("Subscribed to model topic: %s", self._model_topic())
        except Exception as exc:
            LOGGER.exception("Failed to subscribe to model topic")
            with self._lock:
                self._subscribed = False

    def _unsubscribe_mqtt(self) -> None:
        if self.mqtt_client is None:
            return
        try:
            self.mqtt_client.unsubscribe(self._model_topic())
            self.mqtt_client.message_callback_remove(self._model_topic())
        except Exception:
            pass

    def _on_model_message(self, client: Any, userdata: Any, msg: Any) -> None:
        """Handle incoming model message (retained or live)."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            self._process_model_payload(payload, msg.topic)
        except Exception as exc:
            LOGGER.exception("Failed to process model message")

    def _process_model_payload(self, payload: dict[str, Any], topic: str) -> None:
        """Validate and store a received model."""
        version = payload.get("model_version")
        parameters = payload.get("parameters")
        weights_b64 = payload.get("weights_b64")
        chunks = payload.get("chunks")
        chunk_size = payload.get("chunk_size")
        metrics = payload.get("metrics", {})

        if version is None or weights_b64 is None:
            LOGGER.warning("Model payload missing required fields")
            return

        # Reconstruct weights from base64 or chunks
        weights = self._reconstruct_weights(payload)
        if weights is None:
            LOGGER.warning("Failed to reconstruct weights for version %s", version)
            return

        # Validate architecture compatibility
        if not self._validate_architecture(weights):
            with self._lock:
                self._validation_failures += 1
            LOGGER.warning(
                "Model version %s failed architecture validation", version
            )
            return

        # Create checkpoint
        checkpoint = ModelCheckpoint(
            version=int(version),
            weights=weights,
            metrics=metrics,
            received_at=time.time(),
            source_topic=topic,
            parameters=int(parameters) if parameters else sum(w.size for w in weights),
            architecture_hash=self._compute_architecture_hash(weights),
        )

        # Store checkpoint
        with self._lock:
            self._checkpoints[checkpoint.version] = checkpoint
            self._prune_checkpoints()
            self._active_version = checkpoint.version
            self._active_weights = checkpoint.weights
            self._active_architecture_hash = checkpoint.architecture_hash
            self._last_model_received_at = checkpoint.received_at
            self._model_receive_count += 1

        # Persist to local storage
        self._persist_checkpoint(checkpoint)

        LOGGER.info(
            "Deployed model version %d (%d parameters) on gateway %s",
            checkpoint.version,
            checkpoint.parameters,
            self.gateway_id,
        )

    def _reconstruct_weights(self, payload: dict[str, Any]) -> list[np.ndarray] | None:
        """Reconstruct weight arrays from payload (base64 or chunked)."""
        import base64

        try:
            weights_b64 = payload.get("weights_b64")
            if weights_b64:
                data = base64.b64decode(weights_b64)
                # Convert bytes to numpy array (flatten_weights returns float32)
                flat_weights = np.frombuffer(data, dtype=np.float32)
                return unflatten_weights(
                    model=None,
                    flat_weights=flat_weights,
                    shapes=payload.get("shapes", []),
                )

            # Handle chunked delivery
            chunks = payload.get("chunks")
            chunk_size = payload.get("chunk_size")
            if chunks and chunk_size:
                # This would need the full chunked reassembly logic
                # For now, rely on base64 path
                pass
        except Exception:
            LOGGER.exception("Weight reconstruction failed")
        return None

    def _validate_architecture(self, weights: list[np.ndarray]) -> bool:
        """Validate model architecture matches expectations."""
        if self.validation_fn is not None:
            return self.validation_fn(weights)
        if self.expected_architecture_hash is not None:
            return self._compute_architecture_hash(weights) == self.expected_architecture_hash
        return True

    def _compute_architecture_hash(self, weights: list[np.ndarray]) -> str:
        """Compute a hash representing the model architecture."""
        import hashlib

        shapes = tuple(w.shape for w in weights)
        return hashlib.sha256(str(shapes).encode()).hexdigest()[:16]

    def _prune_checkpoints(self) -> None:
        """Keep only the most recent checkpoints up to max_checkpoints."""
        if len(self._checkpoints) <= self.max_checkpoints:
            return
        sorted_versions = sorted(self._checkpoints.keys())
        for version in sorted_versions[:-self.max_checkpoints]:
            del self._checkpoints[version]

    def _persist_checkpoint(self, checkpoint: ModelCheckpoint) -> None:
        """Save checkpoint to local storage."""
        if self.local_storage is None:
            return
        try:
            import base64

            from common.model import flatten_weights

            # Build a temporary model to use flatten_weights
            from common.model import build_model
            n_features = 5  # Default, will be overwritten by inference component
            temp_model = build_model(window_hours=24, n_features=n_features)
            temp_model.set_weights(checkpoint.weights)
            data = flatten_weights(temp_model)
            encoded = base64.b64encode(data).decode("ascii")
            self.local_storage.write(
                f"models/model_v{checkpoint.version}.json",
                json.dumps(
                    {
                        "version": checkpoint.version,
                        "weights_b64": encoded,
                        "shapes": [w.shape for w in checkpoint.weights],
                        "metrics": checkpoint.metrics,
                        "received_at": checkpoint.received_at,
                        "parameters": checkpoint.parameters,
                        "architecture_hash": checkpoint.architecture_hash,
                    }
                ).encode(),
            )
        except Exception:
            LOGGER.exception("Failed to persist model checkpoint")

    def load_latest_checkpoint(self) -> bool:
        """Load the latest checkpoint from local storage on startup."""
        if self.local_storage is None:
            return False
        try:
            import base64

            files = self.local_storage.list("models/")
            if not files:
                return False
            # Find highest version
            latest_file = max(files, key=lambda f: int(f.split("v")[1].split(".")[0]))
            data = json.loads(self.local_storage.read(latest_file).decode())
            weights_data = base64.b64decode(data["weights_b64"])
            # Convert bytes to numpy array
            flat_weights = np.frombuffer(weights_data, dtype=np.float32)
            weights = unflatten_weights(
                model=None,
                flat_weights=flat_weights,
                shapes=data["shapes"],
            )

            checkpoint = ModelCheckpoint(
                version=data["version"],
                weights=weights,
                metrics=data.get("metrics", {}),
                received_at=data["received_at"],
                source_topic="local_storage",
                parameters=data["parameters"],
                architecture_hash=data["architecture_hash"],
            )

            with self._lock:
                self._checkpoints[checkpoint.version] = checkpoint
                self._active_version = checkpoint.version
                self._active_weights = checkpoint.weights
                self._active_architecture_hash = checkpoint.architecture_hash

            LOGGER.info("Loaded model version %d from local storage", checkpoint.version)
            return True
        except Exception:
            LOGGER.exception("Failed to load checkpoint from local storage")
            return False

    def rollback(self, version: int) -> dict[str, Any]:
        """Rollback to a specific model version."""
        with self._lock:
            checkpoint = self._checkpoints.get(version)
            if checkpoint is None:
                return {"status": "error", "message": f"Version {version} not found"}
            self._active_version = checkpoint.version
            self._active_weights = checkpoint.weights
            self._active_architecture_hash = checkpoint.architecture_hash
            return {"status": "ok", "rolled_back_to": version}

    def get_stats(self) -> dict[str, Any]:
        """Get component statistics."""
        with self._lock:
            return {
                "gateway_id": self.gateway_id,
                "subscribed": self._subscribed,
                "active_version": self._active_version,
                "active_architecture_hash": self._active_architecture_hash,
                "checkpoint_count": len(self._checkpoints),
                "available_versions": sorted(self._checkpoints.keys()),
                "model_receive_count": self._model_receive_count,
                "last_model_received_at": self._last_model_received_at,
                "validation_failures": self._validation_failures,
                "has_active_model": self._active_weights is not None,
            }

    def snapshot(self) -> dict[str, Any]:
        """Full state snapshot for monitoring."""
        with self._lock:
            return {
                "component": "ModelDeploymentComponent",
                "gateway_id": self.gateway_id,
                "base_topic": self.base_topic,
                "stats": self.get_stats(),
                "checkpoints": {
                    str(v): {
                        "version": ckpt.version,
                        "parameters": ckpt.parameters,
                        "metrics": ckpt.metrics,
                        "received_at": ckpt.received_at,
                        "architecture_hash": ckpt.architecture_hash,
                    }
                    for v, ckpt in sorted(self._checkpoints.items())
                },
            }


__all__ = ["ModelDeploymentComponent", "ModelCheckpoint"]