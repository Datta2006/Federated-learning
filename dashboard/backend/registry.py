"""Read-only parsing for the coordinator model registry.

The formats below are the ones the existing project already writes:

* ``rounds.csv`` rows from ``server/fl_coordinator.py``
* ``global_vNNNN.json`` model records, plus ``latest.json`` and ``best.json``
* optional ``offline_eval`` JSON written by the Stage 4 experiment

Everything is parsed into JSON-friendly dictionaries so the API, tests, and
frontend share one shape.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any

ROUND_COLUMNS = [
    "round",
    "selected",
    "received",
    "dropped_nodes",
    "bytes_up",
    "bytes_down",
    "round_time_sec",
    "weighted_val_loss",
    "evaluated_version",
    "model_version",
]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return int(number) if number is not None else None


def _split_nodes(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item)]
    return [part for part in str(value).replace(",", " ").split() if part]


def parse_round_rows(text: str) -> list[dict[str, Any]]:
    """Parse ``rounds.csv`` text into normalized round dictionaries."""
    if not text.strip():
        return []
    rows: list[dict[str, Any]] = []
    for raw in csv.DictReader(io.StringIO(text)):
        round_number = _optional_int(raw.get("round"))
        if round_number is None:
            continue
        rows.append(
            {
                "round": round_number,
                "selected": _split_nodes(raw.get("selected")),
                "received": _optional_int(raw.get("received")) or 0,
                "dropped_nodes": _split_nodes(raw.get("dropped_nodes")),
                "bytes_up": _optional_int(raw.get("bytes_up")) or 0,
                "bytes_down": _optional_int(raw.get("bytes_down")) or 0,
                "round_time_sec": _optional_float(raw.get("round_time_sec")),
                "weighted_val_loss": _optional_float(
                    raw.get("weighted_val_loss")
                ),
                "evaluated_version": (raw.get("evaluated_version") or "").strip(),
                "model_version": (raw.get("model_version") or "").strip(),
            }
        )
    rows.sort(key=lambda row: row["round"])
    return rows


def parse_rounds_csv(path: Path) -> list[dict[str, Any]]:
    try:
        return parse_round_rows(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _version_number(version: str) -> int:
    try:
        return int(version.removeprefix("v"))
    except (TypeError, ValueError):
        return -1


def _summary_record(record: dict[str, Any]) -> dict[str, Any]:
    """Keep model records small enough to send on every request."""
    model = record.get("model")
    return {
        "model_version": record.get("model_version"),
        "round": _optional_int(record.get("round")),
        "created_utc": record.get("created_utc"),
        "parameters": _optional_int(record.get("parameters")),
        "weighted_val_loss": _optional_float(record.get("weighted_val_loss")),
        "n_samples": _optional_int(record.get("n_samples")),
        "n_val": _optional_int(record.get("n_val")),
        "sources": list(record.get("sources") or []),
        "kind": record.get("kind"),
        "evaluated_round": _optional_int(record.get("evaluated_round")),
        "model": model if isinstance(model, dict) else {},
    }


def scan_versions(registry_dir: Path) -> list[dict[str, Any]]:
    """Read every ``global_vNNNN.json`` record, newest first."""
    records: list[dict[str, Any]] = []
    for path in registry_dir.glob("global_v*.json"):
        record = read_json(path)
        if record is None:
            continue
        summary = _summary_record(record)
        if not summary["model_version"]:
            continue
        summary["has_weights"] = (
            registry_dir / f"global_{summary['model_version']}.npy"
        ).exists()
        summary["record_path"] = path.name
        records.append(summary)
    records.sort(
        key=lambda item: _version_number(str(item.get("model_version"))),
        reverse=True,
    )
    return records


class RegistryReader:
    """Small read-only adapter over one registry directory."""

    def __init__(
        self,
        registry_dir: Path | None,
        *,
        source: str = "unavailable",
        rounds_csv: Path | None = None,
        chunk_size: int = 16 * 1024,
    ) -> None:
        self.registry_dir = registry_dir
        self.source = source
        self.rounds_csv = (
            rounds_csv
            if rounds_csv is not None
            else (registry_dir / "rounds.csv" if registry_dir else None)
        )
        self.chunk_size = chunk_size
        self._cache_key: tuple[float, float] | None = None
        self._cache: dict[str, Any] | None = None

    def _freshness(self) -> tuple[float, float]:
        if self.registry_dir is None:
            return (0.0, 0.0)
        try:
            latest = (self.registry_dir / "latest.json").stat().st_mtime
        except OSError:
            latest = 0.0
        try:
            rounds = self.rounds_csv.stat().st_mtime if self.rounds_csv else 0.0
        except OSError:
            rounds = 0.0
        return (latest, rounds)

    def snapshot(self) -> dict[str, Any]:
        if self.registry_dir is None:
            return {
                "available": False,
                "source": self.source,
                "registry_path": "unavailable",
                "rounds": [],
                "versions": [],
                "latest": None,
                "best": None,
                "note": "No model registry or rounds.csv was found.",
            }

        key = self._freshness()
        if self._cache is not None and key == self._cache_key:
            return self._cache

        latest = read_json(self.registry_dir / "latest.json")
        best = read_json(self.registry_dir / "best.json")
        rounds = (
            parse_rounds_csv(self.rounds_csv)
            if self.rounds_csv is not None
            else []
        )
        versions = scan_versions(self.registry_dir)
        parameters = _optional_int((latest or {}).get("parameters"))
        bytes_per_model = parameters * 4 if parameters else None
        chunk_count = (
            math.ceil(bytes_per_model / self.chunk_size)
            if bytes_per_model
            else None
        )

        snapshot = {
            "available": latest is not None or bool(rounds),
            "source": self.source,
            "registry_path": _relative(self.registry_dir),
            "rounds_csv": _relative(self.rounds_csv) if self.rounds_csv else None,
            "latest": _summary_record(latest) if latest else None,
            "best": _summary_record(best) if best else None,
            "versions": versions,
            "rounds": rounds,
            "round_count": len(rounds),
            "current_round": rounds[-1]["round"] if rounds else None,
            "latest_model_bytes": bytes_per_model,
            "chunk_size": self.chunk_size,
            "chunk_count": chunk_count,
            "note": (
                "Registry snapshot. Model records are written by the existing "
                "FL coordinator; the dashboard only reads them."
            ),
        }
        self._cache_key = key
        self._cache = snapshot
        return snapshot


def _relative(path: Path | None) -> str:
    if path is None:
        return "unavailable"
    root = Path(__file__).resolve().parents[2]
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
