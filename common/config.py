"""Load project configuration and resolve paths from the repository root."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "common" / "config.json"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read config.json (or *path*) and return it as a dictionary."""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    if "schema_version" not in config:
        raise ValueError(f"{config_path} is missing schema_version")
    return config


def save_config(config: dict[str, Any], path: str | Path | None = None) -> Path:
    """Write *config* as stable, human-readable JSON and return the path."""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return config_path


def resolve_path(path: str | Path) -> Path:
    """Resolve a config-relative path against the repository root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def _node_id_set(value: Any, field: str) -> set[str]:
    if not isinstance(value, list) or not all(
        isinstance(node_id, str) and node_id for node_id in value
    ):
        raise ValueError(f"{field} must be a list of non-empty node IDs")
    return set(value)


def training_node_ids(config: dict[str, Any]) -> set[str]:
    """Node IDs allowed to upload Stage 3 weight updates.

    Falls back to every ``nodes`` entry when ``federated.training_nodes`` is
    absent, so older config files keep working.
    """
    federated = config.get("federated", {})
    configured = federated.get("training_nodes")
    if configured is None:
        return set(config.get("nodes", {}))
    return _node_id_set(configured, "federated.training_nodes")


def inference_only_node_ids(config: dict[str, Any]) -> set[str]:
    """Node IDs that may publish status/health/predictions but never weights."""
    configured = config.get("federated", {}).get("inference_only_nodes", [])
    return _node_id_set(configured, "federated.inference_only_nodes")
