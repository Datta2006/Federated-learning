"""Stage 4 fair comparison: four-node baselines plus FedAvg over MQTT.

Examples::

    # Fair baseline reruns only (node1-node4, 15 epochs, seeds 42/43/44)
    python -m experiments.stage4_experiment --mode baselines

    # Federated runs only, using a private loopback broker
    python -m experiments.stage4_experiment --mode federated --rounds 15

    # Everything, then upsert results.csv and regenerate results.png
    python -m experiments.stage4_experiment --mode all

The federated run spawns real ``node.fl_node`` and ``server.fl_coordinator``
processes, waits for the server to finish, then scores the final registered
model (``latest.json``) with :mod:`server.offline_eval`.  The pooled headline
uses node1-node4 only; node5 is scored separately as unseen data.  The
evaluated checkpoint with the lowest weighted validation loss (``best.json``)
is recorded alongside it for reference.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from baselines.common import (
    aggregate_seed_results,
    make_seed_result,
    plot_results,
    save_aggregate_results,
    utc_now_iso,
)
from common.broker import free_port, start_broker
from common.config import (
    DEFAULT_CONFIG_PATH,
    PROJECT_ROOT,
    inference_only_node_ids,
    load_config,
    resolve_path,
    training_node_ids,
)
from common.improved import prepare_improved_nodes
from common.preprocess import load_raw
from server.offline_eval import evaluate_registry

LOGGER = logging.getLogger(__name__)
FEDERATED_METHOD = "federated_improved_w24"
WINDOW_HOURS = 24


def _spawn(
    module: str,
    arguments: list[str],
    log_path: Path,
) -> tuple[subprocess.Popen, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("wb")
    process = subprocess.Popen(
        [sys.executable, "-m", module, *arguments],
        cwd=PROJECT_ROOT,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    return process, handle


def _stop(process: subprocess.Popen, handle: Any, *, timeout: float = 20.0) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)
    handle.close()


def _log_text(path: Path) -> str:
    return (
        path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    )


def _wait_for_nodes(
    seed_dir: Path,
    processes: dict[str, subprocess.Popen],
    *,
    timeout: float,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for node_id, process in processes.items():
            if process.poll() is not None:
                log = _log_text(seed_dir / f"{node_id}.log")
                raise RuntimeError(
                    f"{node_id} exited during startup with code "
                    f"{process.returncode}:\n{log[-4000:]}"
                )
        if all(
            " online at " in _log_text(seed_dir / f"{node_id}.log")
            for node_id in processes
        ):
            return
        time.sleep(0.5)
    logs = {
        node_id: _log_text(seed_dir / f"{node_id}.log")[-2000:]
        for node_id in processes
    }
    raise TimeoutError(f"nodes did not connect within {timeout:.0f}s: {logs}")


def _read_rounds(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _round_stats(rows: list[dict[str, str]]) -> dict[str, float]:
    if not rows:
        return {
            "completed_rounds": 0,
            "total_bytes_up": 0,
            "total_bytes_down": 0,
            "mean_bytes_up": 0.0,
            "mean_bytes_down": 0.0,
            "mean_bytes_total": 0.0,
            "mean_round_seconds": 0.0,
        }
    up = [float(row["bytes_up"] or 0) for row in rows]
    down = [float(row["bytes_down"] or 0) for row in rows]
    seconds = [float(row["round_time_sec"] or 0) for row in rows]
    return {
        "completed_rounds": len(rows),
        "total_bytes_up": int(sum(up)),
        "total_bytes_down": int(sum(down)),
        "mean_bytes_up": float(np.mean(up)),
        "mean_bytes_down": float(np.mean(down)),
        "mean_bytes_total": float(np.mean(np.add(up, down))),
        "mean_round_seconds": float(np.mean(seconds)),
    }


def run_fair_baselines(
    config: dict[str, Any],
    config_path: str | Path | None,
    *,
    seeds: list[int],
    epochs: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rerun centralized/local-only/persistence on node1-node4 only."""
    from baselines.improved import (
        run_centralized_improved,
        run_local_only_improved,
        run_persistence_improved,
    )

    training = sorted(training_node_ids(config))
    methods = {
        "centralized": f"centralized_improved_w{WINDOW_HOURS}_4nodes",
        "local": f"local_only_improved_w{WINDOW_HOURS}_4nodes",
        "persistence": f"persistence_w{WINDOW_HOURS}_4nodes",
    }
    aggregate_rows: list[dict[str, Any]] = []
    seed_rows: list[dict[str, Any]] = []

    for key, runner in (
        ("centralized", run_centralized_improved),
        ("local", run_local_only_improved),
        ("persistence", run_persistence_improved),
    ):
        method = methods[key]
        rows = []
        for seed in seeds:
            kwargs: dict[str, Any] = {
                "window_hours": WINDOW_HOURS,
                "horizon": 1,
                "seed": seed,
                "method": method,
                "node_ids": training,
            }
            if key != "persistence":
                kwargs["epochs"] = epochs
                kwargs["verbose"] = 0
            rows.append(runner(config_path, **kwargs))
        notes = (
            f"Fair Stage 4 comparison on node1-node4 only; node5 excluded. "
            f"{epochs} epoch(s) for compute parity with {epochs} total federated "
            "local epochs. Raw = filled but unclipped targets; clipped = p99.5 "
            "targets. Headline = raw_unclipped."
            if key != "persistence"
            else "Persistence on node1-node4 test windows only; node5 excluded. "
            "Raw = filled but unclipped targets; clipped = p99.5 targets. "
            "Headline = raw_unclipped."
        )
        aggregate_rows.append(aggregate_seed_results(method, rows, notes))
        seed_rows.extend(rows)
        print(
            f"{method}: seed rows={len(rows)} "
            f"rmse_raw_mean={aggregate_rows[-1]['rmse_raw_mean']:.4f}",
            flush=True,
        )
    return aggregate_rows, seed_rows


def _node_arguments(
    config_path: str,
    node_id: str,
    *,
    host: str,
    port: int,
    seed: int,
    run_seconds: float,
    inference_only: bool,
) -> list[str]:
    arguments = [
        "--config",
        config_path,
        "--node-id",
        node_id,
        "--host",
        host,
        "--port",
        str(port),
        "--seed",
        str(seed),
        "--window-hours",
        str(WINDOW_HOURS),
        "--run-seconds",
        str(run_seconds),
    ]
    if inference_only:
        arguments.append("--inference-only")
    return arguments


def run_federated_seed(
    config: dict[str, Any],
    config_path: str | Path | None,
    *,
    seed: int,
    rounds: int,
    local_epochs: int,
    deadline_sec: float,
    startup_timeout: float,
    min_clients: int,
    work_root: Path,
    broker_mode: str,
) -> dict[str, Any]:
    """Run one federated seed end-to-end and score the registered model."""
    resolved_config = str(
        DEFAULT_CONFIG_PATH if config_path is None else Path(config_path).resolve()
    )
    training = sorted(training_node_ids(config))
    inference = sorted(inference_only_node_ids(config))
    seed_dir = work_root / f"seed-{seed}"
    registry = seed_dir / "registry"
    registry.mkdir(parents=True, exist_ok=True)
    mqtt = config["mqtt"]

    if broker_mode == "private":
        port = free_port()
        host = "127.0.0.1"
        broker = start_broker(seed_dir, port)
    else:
        host = str(mqtt["host"])
        port = int(mqtt["port"])
        broker = None

    print(
        f"seed {seed}: broker={host}:{port} rounds={rounds} "
        f"local_epochs={local_epochs} min_clients={min_clients}",
        flush=True,
    )
    run_seconds = rounds * (deadline_sec + 120.0) + startup_timeout + 600.0
    processes: dict[str, subprocess.Popen] = {}
    handles: dict[str, Any] = {}
    server: subprocess.Popen | None = None
    server_handle = None
    try:
        for node_id in training + inference:
            process, handle = _spawn(
                "node.fl_node",
                _node_arguments(
                    resolved_config,
                    node_id,
                    host=host,
                    port=port,
                    seed=seed,
                    run_seconds=run_seconds,
                    inference_only=node_id in inference,
                ),
                seed_dir / f"{node_id}.log",
            )
            processes[node_id] = process
            handles[node_id] = handle
            time.sleep(0.4)

        _wait_for_nodes(seed_dir, processes, timeout=startup_timeout)
        time.sleep(0.5)

        server, server_handle = _spawn(
            "server.fl_coordinator",
            [
                "--config",
                resolved_config,
                "--host",
                host,
                "--port",
                str(port),
                "--seed",
                str(seed),
                "--rounds",
                str(rounds),
                "--local-epochs",
                str(local_epochs),
                "--deadline-sec",
                str(deadline_sec),
                "--min-clients",
                str(min_clients),
                "--startup-wait-sec",
                "120",
                "--client-wait-sec",
                str(startup_timeout),
                "--window-hours",
                str(WINDOW_HOURS),
                "--model-dir",
                str(registry),
                "--rounds-csv",
                str(registry / "rounds.csv"),
            ],
            seed_dir / "server.log",
        )
        timeout = rounds * (deadline_sec + 180.0) + startup_timeout + 600.0
        try:
            return_code = server.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            server.kill()
            server.wait(timeout=20)
            raise TimeoutError(
                f"seed {seed} server exceeded {timeout:.0f}s"
            ) from exc
        if return_code != 0:
            log = _log_text(seed_dir / "server.log")
            raise RuntimeError(
                f"seed {seed} server exited {return_code}:\n{log[-6000:]}"
            )

        # Stop the training processes before offline scoring so they do not
        # compete for CPU with the evaluator.
        for node_id, process in processes.items():
            _stop(process, handles[node_id])

        rounds_path = registry / "rounds.csv"
        rows = _read_rounds(rounds_path) if rounds_path.exists() else []
        stats = _round_stats(rows)
        if stats["completed_rounds"] == 0:
            log = _log_text(seed_dir / "server.log")
            raise RuntimeError(f"seed {seed} completed no rounds:\n{log[-6000:]}")
        if stats["completed_rounds"] < rounds:
            print(
                f"seed {seed}: WARNING only {stats['completed_rounds']}/{rounds} "
                "rounds completed",
                flush=True,
            )

        latest = evaluate_registry(resolved_config, model_dir=registry, verbose=0)
        latest_version = latest["model_version"]
        best = None
        best_record = None
        best_path = registry / "best.json"
        if best_path.exists():
            best_record = json.loads(best_path.read_text(encoding="utf-8"))
            if str(best_record.get("model_version")) == latest_version:
                best = latest
            else:
                best = evaluate_registry(
                    resolved_config,
                    model_dir=registry,
                    prefer_best=True,
                    verbose=0,
                )

        result = {
            "seed": seed,
            "config_path": resolved_config,
            "broker": f"{host}:{port}",
            "rounds_requested": rounds,
            "rounds_completed": stats["completed_rounds"],
            "local_epochs": local_epochs,
            "latest": latest,
            "best": best,
            "bytes": stats,
            "rounds": rows,
            "created_utc": utc_now_iso(),
        }
        (seed_dir / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        message = (
            f"seed {seed}: latest={latest_version} "
            f"pooled_rmse_raw={latest['pooled_training']['metrics']['rmse_raw']:.4f}"
        )
        if inference:
            unseen = latest["unseen_nodes"][inference[0]]["metrics"]["rmse_raw"]
            message += f" node5_rmse_raw={unseen:.4f}"
        if best is not None:
            message += (
                f" best={best['model_version']} "
                f"val_loss={best.get('weighted_val_loss')}"
            )
        print(message, flush=True)
        return result
    finally:
        for node_id, process in processes.items():
            if node_id in handles:
                _stop(process, handles[node_id])
        if server is not None and server_handle is not None:
            server_handle.close()
        if broker is not None:
            broker.terminate()
            try:
                broker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                broker.kill()


def _raw_bytes(config: dict[str, Any]) -> dict[str, float]:
    """Size of the four nodes' training data if sent as prepared tensors."""
    raw = load_raw(resolve_path(config["dataset_path"]))
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=WINDOW_HOURS,
        node_ids=sorted(training_node_ids(config)),
    )
    n_train = sum(len(item["X_train"]) + len(item["X_val"]) for item in prepared.values())
    n_features = int(next(iter(prepared.values()))["n_features"])
    windowed_bytes = n_train * WINDOW_HOURS * n_features * 4
    raw_rows = n_train + WINDOW_HOURS - 1
    raw_feature_bytes = raw_rows * len(config["features"]) * 4
    return {
        "n_train_windows": int(n_train),
        "window_hours": WINDOW_HOURS,
        "n_features": n_features,
        "raw_windowed_tensor_bytes": int(windowed_bytes),
        "raw_feature_row_bytes": int(raw_feature_bytes),
    }


def _mean_std(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": float(np.mean(array)),
        "std": float(np.std(array, ddof=1)) if array.size > 1 else 0.0,
    }


def aggregate_federated(
    seed_results: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    local_epochs: int,
    min_clients: int,
    bytes_info: dict[str, float],
    summary_path: Path,
) -> dict[str, Any]:
    """Upsert federated_improved_w24 and write the Stage 4 summary JSON."""
    from common.improved import prepare_improved_nodes

    raw = load_raw(resolve_path(config["dataset_path"]))
    prepared = prepare_improved_nodes(
        config,
        raw,
        window_hours=WINDOW_HOURS,
        node_ids=sorted(training_node_ids(config)),
    )
    n_train = sum(len(item["X_train"]) for item in prepared.values())
    parameters = int(seed_results[0]["latest"]["parameters"])

    seed_rows: list[dict[str, Any]] = []
    for result in seed_results:
        metrics = result["latest"]["pooled_training"]["metrics"]
        seed_rows.append(
            make_seed_result(
                FEDERATED_METHOD,
                int(result["seed"]),
                n_train=n_train,
                n_test=int(result["latest"]["pooled_training"]["n_test"]),
                metrics=metrics,
                parameters=parameters,
                epochs=float(result["rounds_completed"] * local_epochs),
                train_seconds=float(
                    result["bytes"]["mean_round_seconds"]
                    * result["rounds_completed"]
                ),
            )
        )

    notes = (
        f"FedAvg over node1-node4 only; node5 is inference-only and scored as "
        f"unseen. Rounds vary by seed per rounds.csv; local_epochs={local_epochs}, "
        f"min_clients={min_clients}. Headline scores the final registered model "
        "(latest.json); best.json tracks the evaluated checkpoint with the lowest "
        "weighted validation loss. Raw = filled but unclipped targets; clipped = "
        "p99.5 targets. Headline = raw_unclipped."
    )
    aggregate = aggregate_seed_results(FEDERATED_METHOD, seed_rows, notes)
    results_path, seed_path = save_aggregate_results(
        config, [aggregate], seed_rows
    )
    plot_path = plot_results(config)
    print(f"saved {results_path}, {seed_path}, {plot_path}", flush=True)

    unseen: dict[str, Any] = {}
    if seed_results[0]["latest"]["unseen_nodes"]:
        node_id = next(iter(seed_results[0]["latest"]["unseen_nodes"]))
        unseen[node_id] = {
            metric: _mean_std(
                [
                    result["latest"]["unseen_nodes"][node_id]["metrics"][metric]
                    for result in seed_results
                ]
            )
            for metric in (
                "rmse_raw",
                "mae_raw",
                "r2_raw",
                "rmse_clipped",
                "mae_clipped",
                "r2_clipped",
            )
        }
        unseen[node_id]["n_test"] = int(
            seed_results[0]["latest"]["unseen_nodes"][node_id]["n_test"]
        )

    summary = {
        "created_utc": utc_now_iso(),
        "method": FEDERATED_METHOD,
        "aggregate": aggregate,
        "seed_results": [
            {
                "seed": result["seed"],
                "rounds_completed": result["rounds_completed"],
                "latest_version": result["latest"]["model_version"],
                "latest_round": result["latest"]["round"],
                "latest_weighted_val_loss": result["latest"].get(
                    "weighted_val_loss"
                ),
                "pooled_metrics": result["latest"]["pooled_training"]["metrics"],
                "unseen_nodes": {
                    node: entry["metrics"]
                    for node, entry in result["latest"]["unseen_nodes"].items()
                },
                "best_version": (
                    None if result["best"] is None else result["best"]["model_version"]
                ),
                "best_round": (
                    None if result["best"] is None else result["best"]["round"]
                ),
                "best_weighted_val_loss": (
                    None
                    if result["best"] is None
                    else result["best"].get("weighted_val_loss")
                ),
                "bytes": result["bytes"],
            }
            for result in seed_results
        ],
        "unseen_node5": unseen,
        "bytes": {
            **bytes_info,
            "one_float32_weight_vector_bytes": parameters * 4,
            "chunks_at_16k": int(
                np.ceil(parameters * 4 / int(config["mqtt"]["chunk_size"]))
            ),
            "mean_wire_bytes_up_per_round": float(
                np.mean(
                    [result["bytes"]["mean_bytes_up"] for result in seed_results]
                )
            ),
            "mean_wire_bytes_down_per_round": float(
                np.mean(
                    [result["bytes"]["mean_bytes_down"] for result in seed_results]
                )
            ),
            "mean_wire_bytes_total_per_round": float(
                np.mean(
                    [result["bytes"]["mean_bytes_total"] for result in seed_results]
                )
            ),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {summary_path}", flush=True)
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nFederated pooled headline (node1-node4, raw unclipped):", flush=True)
    metrics = summary["aggregate"]
    print(
        f"{FEDERATED_METHOD}: "
        f"RMSE={metrics['rmse_raw_mean']:.4f} ± {metrics['rmse_raw_std']:.4f}  "
        f"MAE={metrics['mae_raw_mean']:.4f} ± {metrics['mae_raw_std']:.4f}  "
        f"R2={metrics['r2_raw_mean']:.4f} ± {metrics['r2_raw_std']:.4f}",
        flush=True,
    )
    print("\nNode5 unseen (raw unclipped):", flush=True)
    for node_id, entry in summary["unseen_node5"].items():
        print(
            f"{node_id}: n_test={entry['n_test']} "
            f"RMSE={entry['rmse_raw']['mean']:.4f} ± "
            f"{entry['rmse_raw']['std']:.4f}  "
            f"MAE={entry['mae_raw']['mean']:.4f} ± "
            f"{entry['mae_raw']['std']:.4f}  "
            f"R2={entry['r2_raw']['mean']:.4f} ± "
            f"{entry['r2_raw']['std']:.4f}",
            flush=True,
        )
    print("\nBytes:", flush=True)
    for key in (
        "one_float32_weight_vector_bytes",
        "chunks_at_16k",
        "mean_wire_bytes_up_per_round",
        "mean_wire_bytes_down_per_round",
        "mean_wire_bytes_total_per_round",
        "raw_windowed_tensor_bytes",
        "raw_feature_row_bytes",
    ):
        print(f"  {key}: {summary['bytes'][key]}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 4 fair federated experiment")
    parser.add_argument("--config", default=None)
    parser.add_argument("--mode", choices=["baselines", "federated", "all"], default="all")
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--local-epochs", type=int, default=1)
    parser.add_argument("--baseline-epochs", type=int, default=None)
    parser.add_argument("--deadline-sec", type=float, default=240.0)
    parser.add_argument("--startup-timeout", type=float, default=600.0)
    parser.add_argument("--min-clients", type=int, default=3)
    parser.add_argument("--broker", choices=["private", "config"], default="private")
    parser.add_argument("--work-dir", default=".stage4_runs")
    parser.add_argument("--summary", default="stage4_summary.json")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--verbose", action="count", default=0)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.WARNING if args.verbose == 0 else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if shutil.which("mosquitto") is None:
        raise SystemExit("mosquitto is not installed")

    config = load_config(args.config)
    seeds = [int(part) for part in args.seeds.split(",") if part.strip()]
    training = sorted(training_node_ids(config))
    if args.min_clients > len(training):
        raise SystemExit("min_clients exceeds the number of training nodes")
    baseline_epochs = (
        args.baseline_epochs
        if args.baseline_epochs is not None
        else args.rounds * args.local_epochs
    )
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work_root = Path(args.work_dir).expanduser().resolve() / run_stamp
    summary_path = Path(args.summary).expanduser().resolve()

    print(
        f"mode={args.mode} seeds={seeds} rounds={args.rounds} "
        f"local_epochs={args.local_epochs} baseline_epochs={baseline_epochs} "
        f"training={training} inference={sorted(inference_only_node_ids(config))}",
        flush=True,
    )

    baseline_rows: list[dict[str, Any]] = []
    if args.mode in {"baselines", "all"}:
        baseline_rows, baseline_seed_rows = run_fair_baselines(
            config,
            args.config,
            seeds=seeds,
            epochs=baseline_epochs,
        )
        if not args.no_write:
            results_path, seed_path = save_aggregate_results(
                config, baseline_rows, baseline_seed_rows
            )
            print(f"saved {results_path} and {seed_path}", flush=True)
            print(f"saved {plot_results(config)}", flush=True)

    if args.mode == "baselines":
        return

    seed_results = [
        run_federated_seed(
            config,
            args.config,
            seed=seed,
            rounds=args.rounds,
            local_epochs=args.local_epochs,
            deadline_sec=args.deadline_sec,
            startup_timeout=args.startup_timeout,
            min_clients=args.min_clients,
            work_root=work_root,
            broker_mode=args.broker,
        )
        for seed in seeds
    ]
    bytes_info = _raw_bytes(config)
    if args.no_write:
        print("--no-write set; federated results not saved")
        return
    summary = aggregate_federated(
        seed_results,
        config,
        local_epochs=args.local_epochs,
        min_clients=args.min_clients,
        bytes_info=bytes_info,
        summary_path=summary_path,
    )
    _print_summary(summary)
    print(f"\nper-seed artifacts: {work_root}", flush=True)


if __name__ == "__main__":
    main()
