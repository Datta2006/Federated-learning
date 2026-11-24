"""FastAPI application for AirFed.

Read-only endpoints over existing files plus a WebSocket notification channel.
The MQTT observer is a separate paho client; nothing here publishes to the FL
coordinator or modifies its registry.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from common.worker_protocol import ROUND_STAGES, ProtocolError, TrainingConfig
from simulator.api import create_network_router
from simulator.engine import NetworkSimulator

from .air_quality import AirQualityReader
from .control import ControlError, ControlPublisher
from .demo_prediction import get_available_models, predict_demo_advanced, generate_loss_epochs
from .experiment_api import setup_experiment_routes
from .metrics import build_metrics
from .mqtt_observer import MQTTObserver, build_observer
from .process_manager import ProcessError, ProcessManager
from .registry import RegistryReader
from .settings import Settings, discover_registry
from .telemetry import ROUND_STAGE_DEFINITIONS, TelemetryStore


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


class SocketHub:
    """Thread-safe fan-out from the MQTT worker to WebSocket clients."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._queues.discard(queue)

    def publish_threadsafe(self, payload: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._fanout, payload)
        except RuntimeError:
            return

    def _fanout(self, payload: dict[str, Any]) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # A slow browser must never apply backpressure to the observer.
                pass


@dataclass
class AppState:
    settings: Settings
    registry: RegistryReader
    air_quality: AirQualityReader
    store: TelemetryStore
    observer: MQTTObserver
    hub: SocketHub
    processes: ProcessManager
    controller: ControlPublisher
    started_at: str
    simulator: NetworkSimulator

    def registry_snapshot(self) -> dict[str, Any]:
        # An explicitly configured registry (env var, constructor argument, or
        # a test override) is fixed. Only an auto-discovered registry is
        # re-resolved so a live coordinator run takes over as soon as it writes.
        if self.settings.registry_source not in {
            "unavailable",
            "live_registry",
        } and not self.settings.registry_source.startswith("stage4:"):
            return self.registry.snapshot()
        directory, source = discover_registry()
        if directory is not None and directory != self.registry.registry_dir:
            self.registry = RegistryReader(directory, source=source)
        return self.registry.snapshot()


class SessionRequest(BaseModel):
    action: Literal["start", "pause", "resume", "stop"] = "start"
    config: dict[str, Any] | None = None


class WorkerRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=200)
    role: Literal["training", "inference"] = "training"
    simulation: bool = True
    dummy: bool = False
    prefix: str = "sim"


class StopWorkersRequest(BaseModel):
    ids: list[str] | None = None


class ProcessRequest(BaseModel):
    name: str


class GatewayFlStartRequest(BaseModel):
    gateway_ids: list[str] | None = None
    window_hours: int | None = Field(default=None, ge=1)
    seed: int | None = None
    gateway_count: int | None = Field(default=None, ge=1)


class GatewayFlStopRequest(BaseModel):
    gateway_ids: list[str] | None = None


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()
    hub = SocketHub()

    def on_event(event: dict[str, Any]) -> None:
        hub.publish_threadsafe({"type": "mqtt_event", "event": event})

    store = TelemetryStore(
        nodes=resolved.nodes,
        training_nodes=resolved.training_nodes,
        inference_nodes=resolved.inference_nodes,
        base_topic=resolved.base_topic,
        heartbeat_sec=resolved.heartbeat_sec,
        on_event=on_event,
    )
    registry = RegistryReader(resolved.registry_dir, source=resolved.registry_source)
    air = AirQualityReader(
        resolved.dataset_path, resolved.predictions_path, nodes=resolved.nodes
    )
    observer = build_observer(store, resolved)
    processes = ProcessManager(
        host=resolved.broker_host,
        port=resolved.broker_port,
        base_topic=resolved.base_topic,
    )
    controller = ControlPublisher(
        host=resolved.broker_host,
        port=resolved.broker_port,
        base_topic=resolved.base_topic,
        qos=resolved.mqtt_qos,
    )
    network_simulator = NetworkSimulator()
    state = AppState(
        settings=resolved,
        registry=registry,
        air_quality=air,
        store=store,
        observer=observer,
        hub=hub,
        processes=processes,
        controller=controller,
        started_at=_utc_now(),
        simulator=network_simulator,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        del app
        hub.bind(asyncio.get_running_loop())
        observer.start()

        async def ticker() -> None:
            while True:
                await asyncio.sleep(10.0)
                hub.publish_threadsafe({"type": "tick", "at": _utc_now()})

        async def simulation_ticker() -> None:
            while True:
                await asyncio.sleep(1.0)
                try:
                    state.simulator.advance_if_running(1.0)
                except ValueError:
                    # A malformed simulation config must not take down the API.
                    state.simulator.stop()

        task = asyncio.create_task(ticker())
        simulation_task = asyncio.create_task(simulation_ticker())
        try:
            yield
        finally:
            task.cancel()
            simulation_task.cancel()
            observer.stop()
            processes.stop_all()

    app = FastAPI(
        title="AirFed API",
        version="1.0.0",
        description="Read-only dashboard over the existing federated PM2.5 project.",
        lifespan=lifespan,
    )
    app.state.airfed = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(create_network_router(state.simulator))
    setup_experiment_routes(app)

    def state_of(app: FastAPI) -> AppState:
        return app.state.airfed

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        registry = state.registry_snapshot()
        broker = state.processes.broker_reachable()
        return {
            "ok": True,
            "time": _utc_now(),
            "uptime_since": state.started_at,
            "registry_available": registry["available"],
            "mqtt_enabled": state.settings.mqtt_enabled,
            "broker_reachable": broker,
            "coordinator_running": bool(
                state.processes.status_of("coordinator")
                and state.processes.status_of("coordinator")["running"]
            ),
        }

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        payload["broker"]["host"] = state.settings.broker_host
        payload["broker"]["port"] = state.settings.broker_port
        payload["broker"]["base_topic"] = state.settings.base_topic
        payload["latest_model"] = registry.get("latest")
        payload["best_model"] = registry.get("best")
        payload["registry"].update(
            {
                "updated": registry.get("latest", {}).get("created_utc")
                if registry.get("latest")
                else None,
                "rounds_csv": registry.get("rounds_csv"),
            }
        )
        payload["configured_nodes"] = [
            {
                "id": node_id,
                "year": year,
                "role": (
                    "inference"
                    if node_id in state.settings.inference_nodes
                    else "training"
                ),
            }
            for node_id, year in state.settings.nodes.items()
        ]
        payload["config"] = {
            "base_topic": state.settings.base_topic,
            "heartbeat_sec": state.settings.heartbeat_sec,
            "training_nodes": sorted(state.settings.training_nodes),
            "inference_nodes": sorted(state.settings.inference_nodes),
        }
        payload["predictions"] = state.air_quality.predictions_metadata()
        payload["system"] = {
            "api_started": state.started_at,
            "mqtt_enabled": state.settings.mqtt_enabled,
            "dataset": str(state.settings.dataset_path.name),
        }
        payload["processes"] = state.processes.status()
        payload["processing"] = {
            "session": payload.get("session"),
            "worker_counts": payload.get("worker_counts", {}),
        }
        return payload

    @app.get("/api/rounds")
    def rounds(limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
        registry = state.registry_snapshot()
        status_payload = state.store.status_payload(registry)
        history = registry.get("rounds") or []
        return {
            "available": bool(history),
            "source": registry.get("source"),
            "registry_path": registry.get("registry_path"),
            "round_count": len(history),
            "current_round": status_payload.get("current_round"),
            "round_is_live": status_payload.get("round_is_live", False),
            "round_is_stale": status_payload.get("round_is_stale", False),
            "stage_definition": [
                {"key": key, "label": label}
                for key, label in ROUND_STAGE_DEFINITIONS
            ],
            "history": history[-limit:],
            "loss_history": [
                {
                    "round": row.get("round"),
                    "weighted_val_loss": row.get("weighted_val_loss"),
                    "evaluated_version": row.get("evaluated_version"),
                    "model_version": row.get("model_version"),
                }
                for row in history
            ],
            "note": (
                "Round rows come from the coordinator's rounds.csv. Live stages "
                "are inferred only from observed MQTT metadata, acks, and model "
                "announcements."
            ),
        }

    @app.get("/api/model")
    def model() -> dict[str, Any]:
        registry = state.registry_snapshot()
        latest = registry.get("latest")
        return {
            "available": registry.get("available", False),
            "source": registry.get("source"),
            "registry_path": registry.get("registry_path"),
            "latest": latest,
            "best": registry.get("best"),
            "versions": registry.get("versions", [])[:80],
            "current_round": registry.get("current_round"),
            "round_count": registry.get("round_count"),
            "transfer": {
                "parameters": (latest or {}).get("parameters"),
                "bytes": registry.get("latest_model_bytes"),
                "chunk_size": registry.get("chunk_size"),
                "chunks": registry.get("chunk_count"),
                "dtype": "float32",
            },
            "note": (
                "latest.json follows the newest registered version. best.json "
                "tracks the evaluated checkpoint with the lowest weighted "
                "validation loss."
            ),
        }

    @app.get("/api/metrics")
    def metrics() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = build_metrics(
            results_path=state.settings.results_csv,
            seed_path=state.settings.results_by_seed_csv,
            summary_path=state.settings.stage4_summary_path,
            rounds=registry.get("rounds") or [],
        )
        payload["active_registry"] = {
            "source": registry.get("source"),
            "path": registry.get("registry_path"),
            "latest_model_version": (registry.get("latest") or {}).get(
                "model_version"
            ),
        }
        return payload

    @app.get("/api/models/demo")
    def models_demo() -> dict[str, Any]:
        """Get available demo models for the Testing Model Lab."""
        versions = get_available_models()
        return {
            "available": True,
            "source": "demo_models",
            "versions": versions,
            "note": "Demo models for testing; not trained on real data.",
        }

    @app.post("/api/predict/demo")
    def predict_demo(
        request: dict[str, Any],
    ) -> dict[str, Any]:
        """Run a demo prediction using mock models.

        Request body:
            model_version: The model version to use
            input: List of input features (normalized values 0-1)
        """
        model_version = request.get("model_version", "v1")
        input_data = request.get("input", [0.5, 0.5, 0.5])

        if not isinstance(input_data, list) or len(input_data) == 0:
            raise HTTPException(status_code=400, detail="Invalid input: expected list of numbers")

        try:
            return predict_demo_advanced(
                model_version=str(model_version),
                input_data=[float(v) for v in input_data],
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/api/models/demo/{model_version}/epochs")
    def get_demo_epochs(
        model_version: str,
        epochs: int = Query(default=20, ge=1, le=100),
    ) -> dict[str, Any]:
        """Get synthetic loss epoch data for a demo model.
        
        This generates mock training data showing loss progression over epochs.
        Used for visualization in the Testing Model Lab.
        """
        from .demo_prediction import generate_loss_epochs
        epoch_data = generate_loss_epochs(model_version, epochs=epochs)
        return {
            "model_version": model_version,
            "epochs": len(epoch_data),
            "data": epoch_data,
            "note": "Synthetic training data for demonstration purposes",
        }

    @app.get("/api/air-quality")
    def air_quality(
        node: str | None = Query(default=None),
        limit: int = Query(default=240, ge=24, le=1000),
    ) -> dict[str, Any]:
        registry = state.registry_snapshot()
        selected = node or (
            min(state.settings.inference_nodes)
            if state.settings.inference_nodes
            else (min(state.settings.nodes) if state.settings.nodes else "node5")
        )
        latest_version = (registry.get("latest") or {}).get("model_version")
        try:
            payload = state.air_quality.series(
                selected, limit=limit, latest_model_version=latest_version
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        payload["available_nodes"] = state.air_quality.nodes_payload()
        payload["predictions"] = state.air_quality.predictions_metadata()
        payload["latest_model_version"] = latest_version
        return payload

    @app.get("/api/communication")
    def communication(limit: int = Query(default=120, ge=1, le=400)) -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.communication_payload(registry, limit=limit)
        payload["broker"]["host"] = state.settings.broker_host
        payload["broker"]["port"] = state.settings.broker_port
        payload["broker"]["base_topic"] = state.settings.base_topic
        payload["registry"] = {
            "source": registry.get("source"),
            "path": registry.get("registry_path"),
            "available": registry.get("available", False),
        }
        status_payload = state.store.status_payload(registry)
        payload["session"] = status_payload.get("session")
        payload["round_progress"] = status_payload.get("round_progress")
        payload["round_summaries"] = status_payload.get("round_summaries", [])
        payload["processes"] = state.processes.status()
        return payload

    # -------------------------------------------------------- dynamic control
    def _session_snapshot() -> dict[str, Any] | None:
        return state.store.session_snapshot()

    control_lock = threading.Lock()
    control_cache: dict[str, dict[str, Any]] = {}

    def _ensure_stack_ready(timeout: float = 30.0) -> dict[str, Any]:
        """Start/verify broker + coordinator and prove the control link works.

        Process liveness is not enough: a freshly launched coordinator needs a
        moment to subscribe, and a *previous* run's retained session or log
        lines must never be mistaken for the current one.  Readiness is proven
        by publishing a uniquely-identified ``ping_session`` and waiting for
        the coordinator to echo that exact request id.  Pings are re-published
        until the echo arrives, so a publish that races the subscription is
        simply retried instead of failing the start.
        """
        manager = state.processes
        broker = manager.start_broker()
        launched = manager.start_coordinator()
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        probe_id = uuid.uuid4().hex
        last_publish = 0.0
        while datetime.now(timezone.utc).timestamp() < deadline:
            status = manager.status_of("coordinator")
            if status is not None and not status.get("running"):
                raise ProcessError(
                    "coordinator exited at startup: "
                    + " | ".join(
                        manager.logs("coordinator", lines=12)["lines"][-8:]
                    )
                )
            if status is not None and status.get("running"):
                now = time.monotonic()
                if now - last_publish >= 0.5:
                    try:
                        state.controller.publish(
                            "ping_session", request_id=probe_id
                        )
                    except ControlError:
                        pass
                    last_publish = now
                snapshot = _session_snapshot()
                last = (snapshot or {}).get("last_control") or {}
                if last.get("request_id") == probe_id:
                    return {
                        "broker": broker,
                        "coordinator": launched,
                        "control": "acknowledged",
                        "request_id": probe_id,
                        "session_seen": snapshot is not None,
                    }
            time.sleep(0.2)
        raise ProcessError(
            "coordinator process is up but did not answer a control ping within "
            f"{timeout:.0f}s; check the coordinator log"
        )

    def _control_ack(
        request_id: str, command: str, timeout: float = 20.0
    ) -> dict[str, Any] | None:
        """Wait until the coordinator echoes this request_id in session state."""
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        while datetime.now(timezone.utc).timestamp() < deadline:
            snapshot = _session_snapshot()
            if snapshot:
                last = snapshot.get("last_control") or {}
                if last.get("request_id") == request_id and last.get(
                    "command"
                ) == command:
                    return snapshot
            time.sleep(0.2)
        return None

    def _failure_detail(command: str, request_id: str) -> str:
        tail: list[str] = []
        try:
            tail = state.processes.logs("coordinator", lines=16)["lines"][-10:]
        except ProcessError:
            pass
        return (
            f"coordinator did not acknowledge {command} (request {request_id}) "
            "within the timeout. It may be stopped, unreachable, or not running "
            "in --control mode."
            + (f" Log tail: {' | '.join(tail)}" if tail else "")
        )

    @app.get("/api/session")
    def session() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        return {
            "available": payload.get("session") is not None,
            "session": payload.get("session_view") or payload.get("session"),
            "current_round": payload.get("current_round"),
            "round_progress": payload.get("round_progress"),
            "round_summaries": payload.get("round_summaries", []),
            "workers": payload.get("workers", []),
            "worker_counts": payload.get("worker_counts", {}),
            "infrastructure": payload.get("infrastructure"),
            "activity": payload.get("activity", []),
            "processes": state.processes.status(),
            "stage_definition": [
                {"key": key, "label": label} for key, label in ROUND_STAGES
            ],
        }

    @app.get("/api/fl/gateways")
    def fl_gateways() -> dict[str, Any]:
        """Gateways as independent FL clients, joined with live MQTT state.

        The simulator owns the private shard/model state; the observer owns the
        live worker heartbeats and round summaries.  This endpoint only joins
        the two read-only views and never publishes to the coordinator.
        """
        registry = state.registry_snapshot()
        store_payload = state.store.status_payload(registry)
        engine_payload = state.simulator.fl_clients_payload()
        workers = {
            item.get("worker_id"): item
            for item in store_payload.get("workers", [])
            if item.get("worker_id")
        }
        summaries = store_payload.get("round_summaries") or []
        last_summary = summaries[-1] if summaries else None
        contributions = {
            item.get("node_id"): item
            for item in (last_summary or {}).get("contributions", [])
            if item.get("node_id")
        }
        latest = registry.get("latest")
        gateways: list[dict[str, Any]] = []
        for client in engine_payload.get("gateways", []):
            gateway_id = client["gateway_id"]
            worker_id = client.get("worker_id") or gateway_id
            worker = workers.get(worker_id)
            contribution = contributions.get(worker_id)
            merged = dict(client)
            merged["worker_id"] = worker_id
            merged["worker"] = worker
            merged["online"] = bool(worker and worker.get("online"))
            merged["live_state"] = (
                worker.get("state")
                if worker
                else client.get("worker_state") or client.get("state")
            )
            merged["current_round"] = (
                worker.get("current_round")
                if worker and worker.get("current_round") is not None
                else client.get("current_round")
            )
            merged["aggregation_weight"] = (
                contribution.get("weight") if contribution else None
            )
            merged["last_contribution"] = contribution
            merged["latest_model_version"] = (
                latest.get("model_version") if latest else None
            )
            gateways.append(merged)
        payload = dict(engine_payload)
        payload["gateways"] = gateways
        payload["latest_model"] = latest
        payload["last_round"] = last_summary
        payload["round_count"] = registry.get("round_count")
        return payload

    @app.post("/api/fl/gateways/start")
    def start_fl_gateways(request: GatewayFlStartRequest | None = None) -> dict[str, Any]:
        body = request or GatewayFlStartRequest()
        try:
            payload = state.simulator.start_fl_clients(
                gateway_ids=body.gateway_ids,
                window_hours=body.window_hours,
                seed=body.seed,
                gateway_count=body.gateway_count,
                host=state.settings.broker_host,
                port=state.settings.broker_port,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True, **payload}

    @app.post("/api/fl/gateways/stop")
    def stop_fl_gateways(request: GatewayFlStopRequest | None = None) -> dict[str, Any]:
        body = request or GatewayFlStopRequest()
        return state.simulator.stop_fl_clients(body.gateway_ids)

    @app.get("/api/activity")
    def activity(limit: int = Query(default=80, ge=1, le=400)) -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        return {
            "server_time": payload.get("server_time"),
            "activity": state.store.activity(limit=limit),
            "infrastructure": payload.get("infrastructure"),
            "session": payload.get("session_view"),
            "current_round": payload.get("current_round"),
        }

    @app.get("/api/workers")
    def workers() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        process_status = state.processes.status()
        return {
            "workers": payload.get("workers", []),
            "counts": payload.get("worker_counts", {}),
            "nodes": payload.get("nodes", []),
            "processes": process_status["workers"],
            "coordinator": process_status["coordinator"],
            "broker": process_status["broker"],
            "crashes": process_status["crashes"],
        }

    @app.get("/api/rounds/live")
    def rounds_live() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        from common.worker_protocol import ROUND_STAGES

        return {
            "session": payload.get("session"),
            "current_round": payload.get("current_round"),
            "round_progress": payload.get("round_progress"),
            "summaries": payload.get("round_summaries", []),
            "stage_definition": [
                {"key": key, "label": label} for key, label in ROUND_STAGES
            ],
        }

    @app.post("/api/control/session")
    def control_session(request: SessionRequest) -> dict[str, Any]:
        active_states = {"starting", "waiting", "running", "paused", "stopping"}
        try:
            with control_lock:
                signature = request.action + "|" + json.dumps(
                    request.config or {}, sort_keys=True, default=str
                )
                cached = control_cache.get(signature)
                if cached and time.time() - float(cached.get("_ts", 0)) < 10.0:
                    replay = {
                        key: value for key, value in cached.items() if key != "_ts"
                    }
                    replay["idempotent_replay"] = True
                    return replay

                current = _session_snapshot() or {}
                if request.action == "start":
                    config = TrainingConfig.from_dict(request.config)
                    if current.get("state") in active_states:
                        raise ControlError(
                            "a session is already active "
                            f"({current.get('state')}, {current.get('session_id')}); "
                            "stop it before starting another"
                        )
                    readiness = (
                        _ensure_stack_ready()
                        if state.settings.mqtt_enabled
                        else None
                    )
                    if config.launch_workers and config.simulation_workers > 0:
                        state.processes.start_workers(
                            count=config.simulation_workers,
                            role=config.worker_role,
                            simulation=True,
                            dummy=config.dummy_workers,
                        )
                    command = "start_session"
                    request_id = uuid.uuid4().hex
                    state.controller.publish(
                        command,
                        config=config.to_dict(),
                        request_id=request_id,
                    )
                    ack = _control_ack(request_id, command, timeout=20.0)
                    if ack is None:
                        raise HTTPException(
                            status_code=504,
                            detail=_failure_detail(command, request_id),
                        )
                    result = {
                        "ok": True,
                        "command": command,
                        "request_id": request_id,
                        "acknowledged": True,
                        "config": config.to_dict(),
                        "readiness": readiness,
                        "session": state.store.session_snapshot(),
                        "processes": state.processes.status(),
                    }
                else:
                    command = f"{request.action}_session"
                    status = state.processes.status_of("coordinator")
                    if status is None or not status.get("running"):
                        raise ProcessError(
                            "coordinator is not running; start a session first"
                        )
                    expected = {
                        "pause_session": "paused",
                        "resume_session": "running",
                        "stop_session": "stopped",
                    }[command]
                    request_id = uuid.uuid4().hex
                    state.controller.publish(command, request_id=request_id)
                    ack = _control_ack(request_id, command, timeout=20.0)
                    if ack is None:
                        raise HTTPException(
                            status_code=504,
                            detail=_failure_detail(command, request_id),
                        )
                    result = {
                        "ok": True,
                        "command": command,
                        "request_id": request_id,
                        "acknowledged": True,
                        "expected_state": expected,
                        "session": ack,
                        "processes": state.processes.status(),
                    }
                control_cache[signature] = {**result, "_ts": time.time()}
                if len(control_cache) > 32:
                    control_cache.pop(next(iter(control_cache)))
                return result
        except (ProtocolError, ProcessError, ControlError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/workers/launch")
    def launch_workers(request: WorkerRequest) -> dict[str, Any]:
        try:
            if state.settings.mqtt_enabled:
                _ensure_stack_ready()
            result = state.processes.start_workers(
                count=request.count,
                role=request.role,
                simulation=request.simulation,
                dummy=request.dummy,
                prefix=request.prefix,
            )
            result["processes"] = state.processes.status()
            return result
        except (ProcessError, ControlError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/workers/stop")
    def stop_workers(request: StopWorkersRequest) -> dict[str, Any]:
        try:
            if request.ids:
                stopped = [
                    worker_id
                    for worker_id in request.ids
                    if state.processes.stop_worker(worker_id)
                ]
            else:
                stopped = state.processes.stop_workers()
            return {
                "ok": True,
                "stopped": stopped,
                "processes": state.processes.status(),
            }
        except ProcessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/processes")
    def processes_status() -> dict[str, Any]:
        return state.processes.status()

    @app.post("/api/processes/start")
    def start_process(request: ProcessRequest) -> dict[str, Any]:
        try:
            if request.name == "broker":
                return state.processes.start_broker()
            if request.name == "coordinator":
                if state.settings.mqtt_enabled:
                    state.processes.start_broker()
                return state.processes.start_coordinator()
            if request.name in {"stack", "all"}:
                return _ensure_stack_ready()
            raise ProcessError(
                "name must be one of: broker, coordinator, stack, all"
            )
        except ProcessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/processes/stop")
    def stop_process(request: ProcessRequest) -> dict[str, Any]:
        try:
            if request.name in {"all", "stack"}:
                stopped = state.processes.stop_all()
            else:
                stopped = (
                    [request.name] if state.processes.stop(request.name) else []
                )
            return {
                "ok": True,
                "stopped": stopped,
                "processes": state.processes.status(),
            }
        except ProcessError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/logs")
    def logs(
        name: str = Query(default="coordinator"),
        lines: int = Query(default=120, ge=1, le=1000),
    ) -> dict[str, Any]:
        try:
            return state.processes.logs(name, lines=lines)
        except ProcessError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = state.hub.subscribe()

        async def sender() -> None:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)

        async def receiver() -> None:
            while True:
                raw = await websocket.receive_text()
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict) and message.get("type") == "ping":
                    await websocket.send_json(
                        {"type": "pong", "at": _utc_now()}
                    )

        tasks: list[asyncio.Task[None]] = []
        try:
            registry = state.registry_snapshot()
            snapshot = state.store.status_payload(registry)
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "at": _utc_now(),
                    "data": {
                        "mqtt_enabled": state.settings.mqtt_enabled,
                        "broker": {
                            "host": state.settings.broker_host,
                            "port": state.settings.broker_port,
                            "base_topic": state.settings.base_topic,
                        },
                        "server_time": snapshot.get("server_time"),
                        "session": snapshot.get("session_view"),
                        "current_round": snapshot.get("current_round"),
                        "worker_counts": snapshot.get("worker_counts"),
                        "infrastructure": snapshot.get("infrastructure"),
                        "data_source": snapshot.get("data_source"),
                    },
                }
            )
            tasks = [
                asyncio.create_task(sender()),
                asyncio.create_task(receiver()),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc is not None and not isinstance(
                    exc, (WebSocketDisconnect, RuntimeError)
                ):
                    raise exc
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            for task in tasks:
                task.cancel()
            state.hub.unsubscribe(queue)

    dist = Path(state.settings.frontend_dist)
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    else:

        @app.get("/")
        def root() -> dict[str, Any]:
            return {
                "name": "AirFed API",
                "message": (
                    "Frontend build not found. Run `npm run dev` in "
                    "dashboard/frontend or `npm run build` to serve it here."
                ),
                "docs": "/docs",
                "api": [
                    "/api/status",
                    "/api/rounds",
                    "/api/model",
                    "/api/metrics",
                    "/api/air-quality",
                    "/api/communication",
                    "/api/network/topology",
                    "/api/network/status",
                    "/ws",
                ],
            }

    return app


app = create_app()


def main() -> int:
    import uvicorn

    settings = Settings.load()
    uvicorn.run(
        "dashboard.backend.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
