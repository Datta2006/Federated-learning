"""Export genuine FedAvg predictions for the Air Quality page.

This runs the already-registered federated weights through the project's
existing improved 24 h pipeline and writes a small JSON file consumed by the
dashboard.  It is an offline export, not a live inference service.

Usage (from the repository root, with the project virtualenv active):

    python -m dashboard.backend.export_predictions
    python -m dashboard.backend.export_predictions --nodes node1,node5
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from common.config import load_config, resolve_path
from common.improved import prepare_improved_nodes, reconstruct_pm25
from common.model import build_model_from_config, unflatten_weights
from common.preprocess import load_raw
from dashboard.backend.settings import PREDICTIONS_PATH, discover_registry
from server.offline_eval import resolve_registry

DEFAULT_NODES = "node1,node2,node3,node4,node5"


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _timestamp_string(value: Any) -> str:
    return str(value.astype("datetime64[s]"))


def _number(value: Any, digits: int = 3) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(number, digits)


def export_predictions(
    *,
    config_path: str | Path | None = None,
    model_dir: str | Path | None = None,
    output: str | Path = PREDICTIONS_PATH,
    nodes: list[str] | None = None,
    batch_size: int = 64,
) -> dict[str, Any]:
    config = load_config(config_path)
    if model_dir is None:
        discovered, _ = discover_registry()
        if discovered is None:
            raise SystemExit("no registry found; pass --model-dir explicitly")
        model_dir = discovered
    registry_dir = Path(model_dir).expanduser().resolve()
    record, weights_path = resolve_registry(registry_dir)
    model_config = dict(record.get("model") or {})
    if not model_config:
        raise SystemExit(f"{weights_path} has no model architecture metadata")

    requested = nodes or sorted(config["nodes"])
    unknown = sorted(set(requested).difference(config["nodes"]))
    if unknown:
        raise SystemExit(f"unknown node(s): {unknown}")

    raw = load_raw(resolve_path(config["dataset_path"]))
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=int(model_config.get("window_hours", 24)),
        horizon=int(model_config.get("horizon", 1)),
        delta=bool(model_config.get("delta", True)),
        cyclic_hour=bool(model_config.get("cyclic_hour", True)),
        node_ids=requested,
    )

    weights = np.load(weights_path, allow_pickle=False)
    model = build_model_from_config(model_config)
    unflatten_weights(model, weights)

    raw_lookup = {
        ts.strftime("%Y-%m-%dT%H:%M:%S"): value
        for ts, value in zip(raw["timestamp"], raw["pm2.5"], strict=False)
    }

    series: dict[str, Any] = {}
    for node_id in requested:
        item = prepared[node_id]
        scaled = model.predict(item["X_test"], batch_size=batch_size, verbose=0)
        predicted = reconstruct_pm25(scaled.reshape(-1), item)
        timestamps = [_timestamp_string(value) for value in item["test_timestamps"]]
        series[node_id] = {
            "year": int(item["year"]),
            "n_test": int(len(predicted)),
            "timestamps": timestamps,
            "actual": [_number(raw_lookup.get(ts), 2) for ts in timestamps],
            "actual_filled": [_number(value, 2) for value in item["y_test_raw"]],
            "predicted": [_number(value, 3) for value in predicted],
        }
        print(f"{node_id}: exported {len(predicted)} predictions")

    payload = {
        "created_utc": _utc_now(),
        "model_version": record.get("model_version"),
        "model_dir": str(registry_dir),
        "model_config": model_config,
        "horizon_hours": int(model_config.get("horizon", 1)),
        "timezone": "Dataset local time (no UTC offset in the source CSV)",
        "nodes": series,
        "notes": (
            "Offline predictions from the registered FedAvg model through the "
            "existing common.improved 24 h pipeline, on each node's last-20% "
            "test slice. Not a live sensor feed."
        ),
    }
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output_path}")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=None)
    parser.add_argument("--model-dir", default=None)
    parser.add_argument("--output", default=str(PREDICTIONS_PATH))
    parser.add_argument("--nodes", default=DEFAULT_NODES)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    nodes = [part.strip() for part in args.nodes.split(",") if part.strip()]
    export_predictions(
        config_path=args.config,
        model_dir=args.model_dir,
        output=args.output,
        nodes=nodes,
        batch_size=args.batch_size,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
