"""FastAPI application for AirFed.

Read-only endpoints over existing files plus a WebSocket notification channel.
The MQTT observer is a separate paho client; nothing here publishes to the FL
coordinator or modifies its registry.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .air_quality import AirQualityReader
from .metrics import build_metrics
from .mqtt_observer import MQTTObserver, build_observer
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
    state = AppState(
        settings=resolved,
        registry=registry,
        air_quality=air,
        store=store,
        observer=observer,
        hub=hub,
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
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def state_of(app: FastAPI) -> AppState:
        return app.state.airfed

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        registry = state.registry_snapshot()
        return {
            "ok": True,
            "time": _utc_now(),
            "uptime_since": state.started_at,
            "registry_available": registry["available"],
            "mqtt_enabled": state.settings.mqtt_enabled,
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
            sorted(state.settings.inference_nodes)[0]
            if state.settings.inference_nodes
            else (sorted(state.settings.nodes)[0] if state.settings.nodes else "node5")
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
        return payload

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
