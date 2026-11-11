"""FastAPI application for AirFed.

Read-only endpoints over existing files plus a WebSocket notification channel.
The MQTT observer is a separate paho client; nothing here publishes to the FL
coordinator or modifies its registry.
"""

from __future__ import annotations

import asyncio
import time
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

from .air_quality import AirQualityReader
from .control import ControlError, ControlPublisher
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

        task = asyncio.create_task(ticker())
        try:
            yield
        finally:
            task.cancel()
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
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

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

    def _ensure_stack_ready(timeout: float = 45.0) -> dict[str, Any]:
        """Start/verify broker + coordinator and wait for a retained session."""
        manager = state.processes
        broker = manager.start_broker()
        launched = manager.start_coordinator()
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        while datetime.now(timezone.utc).timestamp() < deadline:
            status = manager.status_of("coordinator")
            if status is not None and not status["running"]:
                raise ProcessError(
                    "coordinator exited at startup: "
                    + " | ".join(
                        manager.logs("coordinator", lines=12)["lines"][-8:]
                    )
                )
            if _session_snapshot() is not None:
                return {"broker": broker, "coordinator": launched}
            time.sleep(0.25)
        raise ProcessError(
            "coordinator did not publish a session state within "
            f"{timeout:.0f}s; check dashboard/backend logs and the coordinator log"
        )

    def _wait_for_session(states: set[str], timeout: float = 15.0) -> dict[str, Any] | None:
        deadline = datetime.now(timezone.utc).timestamp() + timeout
        while datetime.now(timezone.utc).timestamp() < deadline:
            snapshot = _session_snapshot()
            if snapshot and snapshot.get("state") in states:
                return snapshot
            time.sleep(0.2)
        return _session_snapshot()

    @app.get("/api/session")
    def session() -> dict[str, Any]:
        registry = state.registry_snapshot()
        payload = state.store.status_payload(registry)
        return {
            "available": payload.get("session") is not None,
            "session": payload.get("session"),
            "current_round": payload.get("current_round"),
            "round_progress": payload.get("round_progress"),
            "round_summaries": payload.get("round_summaries", []),
            "workers": payload.get("workers", []),
            "worker_counts": payload.get("worker_counts", {}),
            "processes": state.processes.status(),
            "stage_definition": [
                {"key": key, "label": label} for key, label in ROUND_STAGES
            ],
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
        try:
            if request.action == "start":
                config = TrainingConfig.from_dict(request.config)
                readiness = (
                    _ensure_stack_ready() if state.settings.mqtt_enabled else None
                )
                if config.launch_workers and config.simulation_workers > 0:
                    state.processes.start_workers(
                        count=config.simulation_workers,
                        role=config.worker_role,
                        simulation=True,
                    )
                state.controller.publish(
                    "start_session", config=config.to_dict()
                )
                snapshot = _wait_for_session(
                    {"waiting", "running", "paused"}, timeout=20.0
                )
                return {
                    "ok": True,
                    "command": "start_session",
                    "config": config.to_dict(),
                    "readiness": readiness,
                    "session": snapshot,
                    "processes": state.processes.status(),
                }
            command = f"{request.action}_session"
            status = state.processes.status_of("coordinator")
            if status is None or not status["running"]:
                raise ProcessError(
                    "coordinator is not running; start a session first"
                )
            state.controller.publish(command)
            expected = {
                "pause_session": "paused",
                "resume_session": "running",
                "stop_session": "stopped",
            }[command]
            snapshot = _wait_for_session({expected}, timeout=20.0)
            return {
                "ok": True,
                "command": command,
                "session": snapshot,
                "processes": state.processes.status(),
            }
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
        try:
            await websocket.send_json(
                {
                    "type": "hello",
                    "at": _utc_now(),
                    "data": {
                        "mqtt_enabled": state.settings.mqtt_enabled,
                        "broker": {
                            "host": state.settings.broker_host,
                            "port": state.settings.broker_port,
                            "base_topic": state.settings.base_topic,
                        },
                    },
                }
            )
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
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
