"""Dedicated, bounded storage for gateway-side federated-learning state.

Telemetry buffering lives in :class:`simulator.gateway.LocalStorageComponent`
and must stay telemetry-only.  Federated learning has a different lifecycle
(local weights, checkpoints, round metadata, partition provenance), so it gets
its own component and its own directory.

Nothing in this module can carry a raw sensor reading: checkpoints are float32
weight vectors, and metadata is JSON written by the FL client itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np

DEFAULT_MAX_CHECKPOINTS = 3


def _safe_dirname(gateway_id: str) -> str:
    digest = hashlib.sha256(str(gateway_id).encode("utf-8")).hexdigest()[:8]
    from simulator.fl_identity import sanitize_component

    return f"{sanitize_component(gateway_id)}-{digest}"


class FLStorageComponent:
    """Thread-safe JSON state plus a bounded set of local weight checkpoints."""

    def __init__(
        self,
        gateway_id: str,
        *,
        root: str | Path | None = None,
        max_checkpoints: int = DEFAULT_MAX_CHECKPOINTS,
    ) -> None:
        if max_checkpoints < 1:
            raise ValueError("max_checkpoints must be at least 1")
        self.gateway_id = str(gateway_id)
        self.max_checkpoints = int(max_checkpoints)
        self._lock = threading.RLock()
        base = (
            Path(root)
            if root is not None
            else Path(__file__).resolve().parents[1]
            / ".airfed_runtime"
            / "fl_gateways"
        )
        self.directory = Path(base) / _safe_dirname(self.gateway_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.state_path = self.directory / "state.json"

    # ------------------------------------------------------------------ state
    def read_state(self) -> dict[str, Any]:
        with self._lock:
            if not self.state_path.exists():
                return {}
            try:
                with self.state_path.open("r", encoding="utf-8") as handle:
                    value = json.load(handle)
            except (OSError, ValueError):
                return {}
            return value if isinstance(value, dict) else {}

    def write_state(self, **fields: Any) -> dict[str, Any]:
        """Merge ``fields`` into the persisted state atomically."""
        with self._lock:
            state = self.read_state()
            state.update(fields)
            state["gateway_id"] = self.gateway_id
            tmp = self.state_path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.state_path)
            return state

    def record_partition(self, partition: dict[str, Any]) -> None:
        """Persist the gateway-local partition provenance (ids/sizes only)."""
        safe = {
            key: partition.get(key)
            for key in (
                "worker_id",
                "gateway_index",
                "gateway_count",
                "years",
                "shard_indices",
                "n_samples",
                "n_val",
                "source_rows",
                "dataset",
            )
            if key in partition
        }
        self.write_state(partition=safe)

    def record_round(self, round_number: int, metadata: dict[str, Any]) -> None:
        with self._lock:
            state = self.read_state()
            history = list(state.get("rounds") or [])
            history = [
                item
                for item in history
                if int(item.get("round", -1)) != int(round_number)
            ]
            history.append(
                {
                    "round": int(round_number),
                    "n_samples": metadata.get("n_samples"),
                    "n_val": metadata.get("n_val"),
                    "val_loss": metadata.get("val_loss"),
                    "model_version": metadata.get("model_version"),
                    "sha256": metadata.get("sha256"),
                    "ack": metadata.get("ack"),
                }
            )
            history.sort(key=lambda item: int(item["round"]))
            state["rounds"] = history[-20:]
            state["last_round"] = int(round_number)
            state["updated_utc"] = metadata.get("updated_utc")
            tmp = self.state_path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(state, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, self.state_path)

    # ------------------------------------------------------------ checkpoints
    def save_checkpoint(
        self,
        round_number: int,
        weights: np.ndarray,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """Atomically save one float32 weight vector and prune old checkpoints."""
        array = np.asarray(weights, dtype=np.float32)
        if array.ndim != 1:
            raise ValueError("FL checkpoints must be a flat weight vector")
        payload = {
            "gateway_id": self.gateway_id,
            "round": int(round_number),
            "size": int(array.size),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
            **(metadata or {}),
        }
        with self._lock:
            target = self.directory / f"checkpoint_v{int(round_number):04d}"
            np.save(target.with_suffix(".npy"), array, allow_pickle=False)
            tmp = target.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp, target.with_suffix(".json"))
            self._prune_checkpoints()
            return target.with_suffix(".npy")

    def _checkpoints(self) -> list[Path]:
        return sorted(self.directory.glob("checkpoint_v*.npy"))

    def _prune_checkpoints(self) -> None:
        checkpoints = self._checkpoints()
        for old in checkpoints[: max(0, len(checkpoints) - self.max_checkpoints)]:
            for path in (old, old.with_suffix(".json")):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def latest_checkpoint(self) -> dict[str, Any] | None:
        with self._lock:
            checkpoints = self._checkpoints()
            if not checkpoints:
                return None
            path = checkpoints[-1]
            meta = {}
            try:
                with path.with_suffix(".json").open("r", encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, ValueError):
                meta = {}
            return {"path": str(path), "metadata": meta}

    # ----------------------------------------------------------------- stats
    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            checkpoints = self._checkpoints()
            state = self.read_state()
            return {
                "directory": str(self.directory),
                "max_checkpoints": self.max_checkpoints,
                "checkpoint_count": len(checkpoints),
                "latest_checkpoint": checkpoints[-1].name if checkpoints else None,
                "last_round": state.get("last_round"),
                "partition": state.get("partition"),
                "rounds_recorded": len(state.get("rounds") or []),
                "size_bytes": sum(
                    path.stat().st_size for path in self.directory.glob("*")
                ),
            }

    def clear(self) -> None:
        """Remove this gateway's FL state (never touches telemetry storage)."""
        with self._lock:
            for path in self.directory.glob("*"):
                if path.is_file():
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass


__all__ = ["DEFAULT_MAX_CHECKPOINTS", "FLStorageComponent"]
