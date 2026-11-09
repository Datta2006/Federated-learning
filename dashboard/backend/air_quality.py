"""Historical air-quality replay and genuine model-prediction alignment.

Two data sources are possible, and the API labels which one is in use:

``fedavg_offline``
    A JSON file produced by ``python -m dashboard.backend.export_predictions``.
    It runs the existing registered FedAvg weights through the existing
    ``common.improved`` pipeline.  Nothing is simulated.

``persistence_reference``
    When no export exists, the endpoint computes the project's existing
    persistence baseline (next hour equals the current observed hour).  The UI
    labels this as a reference, not as a FedAvg prediction.

In both cases the temperature/RH series and PM2.5 observations are historical
replay from ``data/beijing_pm25.csv``.  There is no real-time sensor feed in
this repository, and the API says so explicitly.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

DATASET_NAME = "Beijing PM2.5 (PRSA) 2010-2014"
TIMEZONE_NOTE = "Dataset local time (no UTC offset in the source CSV)"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NA", "NAN", "NULL"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def relative_humidity(temp_c: float, dewpoint_c: float) -> float:
    """Magnus formula, matching ``common.preprocess.derive_relative_humidity``."""
    numerator = math.exp(17.625 * dewpoint_c / (243.04 + dewpoint_c))
    denominator = math.exp(17.625 * temp_c / (243.04 + temp_c))
    return max(0.0, min(100.0, 100.0 * numerator / denominator))


def parse_dataset_rows(text: str) -> list[dict[str, Any]]:
    """Parse the raw PRSA CSV into display rows (pure, testable)."""
    rows: list[dict[str, Any]] = []
    filled: float | None = None
    for raw in csv.DictReader(text.splitlines()):
        try:
            year = int(raw["year"])
            month = int(raw["month"])
            day = int(raw["day"])
            hour = int(raw["hour"])
        except (KeyError, TypeError, ValueError):
            continue
        pm25 = _float_or_none(raw.get("pm2.5"))
        temp = _float_or_none(raw.get("TEMP"))
        dewp = _float_or_none(raw.get("DEWP"))
        if pm25 is not None:
            filled = pm25
        rows.append(
            {
                "ts": (
                    f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:00:00"
                ),
                "year": year,
                "pm25": pm25,
                "pm25_filled": filled,
                "temp": temp,
                "rh": (
                    round(relative_humidity(temp, dewp), 2)
                    if temp is not None and dewp is not None
                    else None
                ),
            }
        )
    # Backfill leading gaps so the first model target has a current value,
    # mirroring fill_pm25_series' interpolate(limit_direction="both").
    first = next((row["pm25"] for row in rows if row["pm25"] is not None), None)
    if first is not None:
        for row in rows:
            if row["pm25_filled"] is not None:
                break
            row["pm25_filled"] = first
    return rows


def _downsample(points: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or len(points) <= limit:
        return points
    if limit == 1:
        return [points[-1]]
    step = (len(points) - 1) / (limit - 1)
    indices = sorted({round(index * step) for index in range(limit)})
    return [points[index] for index in indices]


class AirQualityReader:
    def __init__(
        self,
        dataset_path: Path,
        predictions_path: Path,
        *,
        nodes: dict[str, int],
    ) -> None:
        self.dataset_path = dataset_path
        self.predictions_path = predictions_path
        self.nodes = dict(nodes)
        self._dataset_key: float | None = None
        self._dataset: dict[int, list[dict[str, Any]]] | None = None
        self._predictions_key: float | None = None
        self._predictions: dict[str, Any] | None = None

    # ------------------------------------------------------------- loading
    def _load_dataset(self) -> dict[int, list[dict[str, Any]]]:
        try:
            key = self.dataset_path.stat().st_mtime
        except OSError as exc:
            raise FileNotFoundError(
                f"dataset not found: {self.dataset_path}"
            ) from exc
        if self._dataset is not None and key == self._dataset_key:
            return self._dataset
        text = self.dataset_path.read_text(encoding="utf-8")
        rows = parse_dataset_rows(text)
        by_year: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            by_year.setdefault(row["year"], []).append(row)
        self._dataset = by_year
        self._dataset_key = key
        return by_year

    def _load_predictions(self) -> dict[str, Any] | None:
        try:
            key = self.predictions_path.stat().st_mtime
        except OSError:
            self._predictions = None
            self._predictions_key = None
            return None
        if self._predictions is not None and key == self._predictions_key:
            return self._predictions
        try:
            value = json.loads(self.predictions_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            value = None
        self._predictions = value if isinstance(value, dict) else None
        self._predictions_key = key
        return self._predictions

    # ------------------------------------------------------------- queries
    def nodes_payload(self) -> list[dict[str, Any]]:
        predictions = self._load_predictions()
        available = set((predictions or {}).get("nodes", {}))
        return [
            {
                "id": node_id,
                "year": year,
                "predictions_available": node_id in available,
            }
            for node_id, year in self.nodes.items()
        ]

    def series(
        self,
        node_id: str,
        *,
        limit: int = 240,
        latest_model_version: str | None = None,
    ) -> dict[str, Any]:
        if node_id not in self.nodes:
            raise ValueError(
                f"unknown node {node_id!r}; expected one of {sorted(self.nodes)}"
            )
        year = int(self.nodes[node_id])
        by_year = self._load_dataset()
        if year not in by_year:
            raise ValueError(f"no dataset rows for {node_id} (year {year})")
        limit = max(1, min(int(limit), 1000))
        predictions = self._load_predictions()
        node_predictions = (predictions or {}).get("nodes", {}).get(node_id)
        dataset_by_ts = {row["ts"]: row for row in by_year[year]}

        if isinstance(node_predictions, dict):
            points = self._model_points(
                node_predictions, dataset_by_ts, limit=limit
            )
            prediction_version = (predictions or {}).get("model_version")
            stale = bool(
                latest_model_version
                and prediction_version
                and prediction_version != latest_model_version
            )
            return self._payload(
                node_id=node_id,
                year=year,
                points=points,
                prediction_source="fedavg_offline",
                prediction_label="FedAvg 1-hour-ahead prediction",
                model_version=prediction_version,
                prediction_stale=stale,
                note=(
                    "Predictions are from an offline run of the registered "
                    "FedAvg model through the existing 24 h pipeline, not a "
                    "live inference stream. Test-split rows only."
                ),
                actual_note=(
                    "PM2.5 targets use the existing forward-fill preprocessing; "
                    "raw observations are shown where available."
                ),
            )

        points = self._persistence_points(by_year[year], limit=limit)
        return self._payload(
            node_id=node_id,
            year=year,
            points=points,
            prediction_source="persistence_reference",
            prediction_label="Persistence 1-hour reference (not model output)",
            model_version=None,
            prediction_stale=False,
            note=(
                "No FedAvg prediction export exists for this node. The line is "
                "the project's existing persistence baseline: next hour equals "
                "the current observed value. Run the export command in "
                "dashboard/README.md to plot real model predictions."
            ),
            actual_note=(
                "Historical replay only. The repository has no real-time sensor "
                "feed, so this is not live telemetry."
            ),
        )

    def _model_points(
        self,
        node_predictions: dict[str, Any],
        dataset_by_ts: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        timestamps = list(node_predictions.get("timestamps") or [])
        actual = list(node_predictions.get("actual") or [])
        actual_filled = list(node_predictions.get("actual_filled") or [])
        predicted = list(node_predictions.get("predicted") or [])
        count = min(len(timestamps), len(actual), len(predicted))
        points: list[dict[str, Any]] = []
        for index in range(count):
            ts = str(timestamps[index])
            dataset = dataset_by_ts.get(ts, {})
            points.append(
                {
                    "ts": ts,
                    "actual": _float_or_none(actual[index]),
                    "actual_filled": (
                        _float_or_none(actual_filled[index])
                        if index < len(actual_filled)
                        else _float_or_none(actual[index])
                    ),
                    "predicted": _float_or_none(predicted[index]),
                    "temp": dataset.get("temp"),
                    "rh": dataset.get("rh"),
                }
            )
        return _downsample(points[-limit:], limit)

    def _persistence_points(
        self, rows: list[dict[str, Any]], *, limit: int
    ) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        for index in range(1, len(rows)):
            row = rows[index]
            previous = rows[index - 1]
            points.append(
                {
                    "ts": row["ts"],
                    "actual": row["pm25"],
                    "actual_filled": row["pm25_filled"],
                    "predicted": previous["pm25_filled"],
                    "temp": row["temp"],
                    "rh": row["rh"],
                }
            )
        return _downsample(points[-limit:], limit)

    def _payload(
        self,
        *,
        node_id: str,
        year: int,
        points: list[dict[str, Any]],
        prediction_source: str,
        prediction_label: str,
        model_version: str | None,
        prediction_stale: bool,
        note: str,
        actual_note: str,
    ) -> dict[str, Any]:
        return {
            "node": node_id,
            "year": year,
            "mode": "historical_replay",
            "is_realtime": False,
            "dataset": {
                "name": DATASET_NAME,
                "path": _relative(self.dataset_path),
                "timezone": TIMEZONE_NOTE,
            },
            "prediction_source": prediction_source,
            "prediction_label": prediction_label,
            "model_version": model_version,
            "prediction_stale": prediction_stale,
            "note": note,
            "actual_note": actual_note,
            "units": {"pm25": "µg/m³", "temp": "°C", "rh": "%"},
            "range": {
                "start": points[0]["ts"] if points else None,
                "end": points[-1]["ts"] if points else None,
                "points": len(points),
            },
            "series": points,
        }

    def predictions_metadata(self) -> dict[str, Any]:
        predictions = self._load_predictions()
        if predictions is None:
            return {"available": False, "source": "unavailable"}
        return {
            "available": True,
            "source": _relative(self.predictions_path),
            "created_utc": predictions.get("created_utc"),
            "model_version": predictions.get("model_version"),
            "nodes": sorted((predictions.get("nodes") or {}).keys()),
            "horizon_hours": predictions.get("horizon_hours"),
            "timezone": predictions.get("timezone"),
        }


def _relative(path: Path) -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
