"""Configuration and registry discovery for the AirFed dashboard.

The dashboard must work against both the live coordinator registry
(``server/model_registry``) and the immutable Stage 4 experiment registries
under ``.stage4_runs``.  Nothing here writes to either location.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_ROOT = PROJECT_ROOT / "dashboard"
BACKEND_ROOT = DASHBOARD_ROOT / "backend"
FRONTEND_DIST = DASHBOARD_ROOT / "frontend" / "dist"
PREDICTIONS_PATH = BACKEND_ROOT / "data" / "predictions.json"

DEFAULT_BROKER_HOST = "127.0.0.1"
DEFAULT_BROKER_PORT = 1883
DEFAULT_API_PORT = 8010


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _registry_marker(directory: Path) -> float:
    """Freshness of a registry, based on the files the coordinator writes."""
    return max(
        _mtime(directory / "latest.json"),
        _mtime(directory / "rounds.csv"),
        _mtime(directory / "best.json"),
    )


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings.

    Environment overrides are intentionally small and documented in
    ``dashboard/README.md``.  A path passed to :class:`RegistryReader` wins
    over everything except an explicit ``AIRFED_REGISTRY_DIR``.
    """

    broker_host: str
    broker_port: int
    broker_client_id: str
    mqtt_enabled: bool
    mqtt_qos: int
    base_topic: str
    heartbeat_sec: float
    nodes: dict[str, int]
    training_nodes: set[str]
    inference_nodes: set[str]
    dataset_path: Path
    results_csv: Path
    results_by_seed_csv: Path
    stage4_summary_path: Path
    predictions_path: Path
    registry_dir: Path | None
    registry_source: str
    frontend_dist: Path
    api_host: str
    api_port: int

    @classmethod
    def load(cls, *, registry_dir: str | Path | None = None) -> "Settings":
        config = _load_project_config()
        mqtt = dict(config.get("mqtt", {}))
        paths = dict(config.get("paths", {}))
        federated = dict(config.get("federated", {}))
        nodes = {
            str(node_id): int(year)
            for node_id, year in dict(config.get("nodes", {})).items()
        }
        training_nodes = set(
            federated.get("training_nodes") or list(nodes)
        )
        inference_nodes = set(federated.get("inference_only_nodes") or [])

        broker_host = os.getenv("AIRFED_BROKER_HOST", str(mqtt.get("host", DEFAULT_BROKER_HOST)))
        broker_port = int(os.getenv("AIRFED_BROKER_PORT", mqtt.get("port", DEFAULT_BROKER_PORT)))
        base_topic = os.getenv("AIRFED_BASE_TOPIC", str(mqtt.get("base_topic", "aq")))
        heartbeat = float(mqtt.get("heartbeat_sec", 10))
        qos = int(os.getenv("AIRFED_MQTT_QOS", mqtt.get("qos", 1)))

        explicit = os.getenv("AIRFED_REGISTRY_DIR")
        if explicit:
            resolved_registry = _absolute(Path(explicit))
            source = "env"
        elif registry_dir is not None:
            resolved_registry = _absolute(Path(registry_dir))
            source = "argument"
        else:
            resolved_registry, source = discover_registry()

        dataset = os.getenv(
            "AIRFED_DATASET", str(paths.get("dataset_path", "data/beijing_pm25.csv"))
        )
        results = os.getenv("AIRFED_RESULTS_CSV", "results.csv")
        results_by_seed = os.getenv("AIRFED_RESULTS_BY_SEED_CSV", "results_by_seed.csv")
        summary = os.getenv("AIRFED_SUMMARY_JSON", "stage4_summary.json")
        predictions = os.getenv("AIRFED_PREDICTIONS", str(PREDICTIONS_PATH))

        return cls(
            broker_host=broker_host,
            broker_port=broker_port,
            broker_client_id=os.getenv("AIRFED_CLIENT_ID", "airfed-dashboard"),
            mqtt_enabled=_env_bool("AIRFED_MQTT_ENABLED", True),
            mqtt_qos=qos,
            base_topic=base_topic,
            heartbeat_sec=heartbeat,
            nodes=nodes,
            training_nodes=training_nodes,
            inference_nodes=inference_nodes,
            dataset_path=_absolute(Path(dataset)),
            results_csv=_absolute(Path(results)),
            results_by_seed_csv=_absolute(Path(results_by_seed)),
            stage4_summary_path=_absolute(Path(summary)),
            predictions_path=_absolute(Path(predictions)),
            registry_dir=resolved_registry,
            registry_source=source,
            frontend_dist=_absolute(
                Path(os.getenv("AIRFED_FRONTEND_DIST", str(FRONTEND_DIST)))
            ),
            api_host=os.getenv("AIRFED_API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("AIRFED_API_PORT", DEFAULT_API_PORT)),
        )


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _load_project_config() -> dict:
    """Load the existing project config without failing on a missing file."""
    try:
        from common.config import load_config

        return load_config()
    except Exception:  # pragma: no cover - dashboard still works without config
        return {}


def discover_registry() -> tuple[Path | None, str]:
    """Pick the freshest existing registry.

    Priority is decided by file modification time rather than directory name.
    That means a live run in ``server/model_registry`` wins as soon as the
    coordinator writes to it, while a completed Stage 4 run remains visible
    before that.
    """
    candidates: list[tuple[float, Path, str]] = []

    live = PROJECT_ROOT / "server" / "model_registry"
    live_freshness = _registry_marker(live)
    if live_freshness > 0:
        candidates.append((live_freshness, live, "live_registry"))

    for marker in sorted(
        (PROJECT_ROOT / ".stage4_runs").glob("*/seed-*/registry/latest.json")
    ):
        directory = marker.parent
        freshness = _registry_marker(directory)
        seed_name = directory.parent.name
        candidates.append((freshness, directory, f"stage4:{seed_name}"))

    if not candidates:
        return None, "unavailable"

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, directory, source = candidates[0]
    return directory.resolve(), source


def registry_location(path: Path | None) -> str:
    """Short, human-readable registry path for API provenance badges."""
    if path is None:
        return "unavailable"
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
