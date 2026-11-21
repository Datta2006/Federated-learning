"""FastAPI adapter for the network simulator.

Every route lives under ``/api/network`` so it cannot collide with the existing
federated-learning dashboard routes.  All mutation is delegated to
:class:`simulator.engine.NetworkSimulator`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from simulator.engine import NetworkSimulator
from simulator.entities import Position


class PositionModel(BaseModel):
    x: float = 50.0
    y: float = 35.0
    location: str | None = None

    def to_domain(self) -> Position:
        return Position(x=self.x, y=self.y, location=self.location)


class GatewayCreate(BaseModel):
    gateway_id: str | None = None
    name: str | None = None
    position: PositionModel | None = None
    available: bool = True
    transmission_range_m: float = Field(default=600.0, gt=0)
    storage_capacity_mb: float = Field(default=512.0, gt=0)
    storage_used_mb: float = Field(default=0.0, ge=0)


class SensorCreate(BaseModel):
    node_id: str | None = None
    name: str | None = None
    gateway_id: str | None = None
    position: PositionModel | None = None
    available: bool = True
    battery_level: float = Field(default=100.0, ge=0, le=100)
    transmission_range_m: float = Field(default=250.0, gt=0)
    data_source: str = "simulated_sensor"


class LinkCreate(BaseModel):
    link_id: str | None = None
    source: str
    destination: str
    quality: float = Field(default=1.0, ge=0, le=1)
    etx: float = Field(default=1.0, ge=1)
    latency_ms: float = Field(default=10.0, ge=0)
    packet_loss: float = Field(default=0.0, ge=0, le=1)
    available: bool = True
    bandwidth_kbps: float = Field(default=250.0, gt=0)
    bidirectional: bool = True


class GatewayAssignment(BaseModel):
    gateway_id: str | None = None


class AvailabilityUpdate(BaseModel):
    available: bool


class AdvanceRequest(BaseModel):
    seconds: float | None = Field(default=None, ge=0)


def create_network_router(simulator: NetworkSimulator) -> APIRouter:
    """Build the ``/api/network`` router around one engine instance."""
    router = APIRouter(prefix="/api/network", tags=["network-simulation"])

    def _failed(exc: ValueError) -> HTTPException:
        return HTTPException(status_code=400, detail=str(exc))

    @router.get("/topology")
    def topology() -> dict[str, Any]:
        return simulator.snapshot()

    @router.get("/nodes")
    def nodes() -> dict[str, Any]:
        items = simulator.nodes_payload()
        return {"count": len(items), "nodes": items}

    @router.get("/sensors")
    def sensors() -> dict[str, Any]:
        items = simulator.sensors_payload()
        return {"count": len(items), "sensors": items}

    @router.get("/gateways")
    def gateways() -> dict[str, Any]:
        items = simulator.gateways_payload()
        return {"count": len(items), "gateways": items}

    @router.get("/links")
    def links() -> dict[str, Any]:
        items = simulator.links_payload()
        return {"count": len(items), "links": items}

    @router.get("/status")
    def status() -> dict[str, Any]:
        return simulator.status_payload()

    @router.get("/config")
    def configuration() -> dict[str, Any]:
        return simulator.configuration_payload()

    @router.get("/readings/{node_id}")
    def readings(
        node_id: str, limit: int = Query(default=50, ge=1, le=500)
    ) -> dict[str, Any]:
        try:
            return simulator.readings_payload(node_id, limit=limit)
        except ValueError as exc:
            raise _failed(exc) from exc

    @router.post("/simulation/start")
    def start() -> dict[str, Any]:
        return {"ok": True, "simulation": simulator.start()}

    @router.post("/simulation/stop")
    def stop() -> dict[str, Any]:
        return {"ok": True, "simulation": simulator.stop()}

    @router.post("/simulation/reset")
    def reset() -> dict[str, Any]:
        return {"ok": True, "simulation": simulator.reset()}

    @router.post("/simulation/advance")
    def advance(request: AdvanceRequest | None = None) -> dict[str, Any]:
        try:
            payload = simulator.advance(request.seconds if request else None)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "simulation": payload}

    @router.post("/nodes")
    def create_sensor(request: SensorCreate) -> dict[str, Any]:
        try:
            node = simulator.create_sensor_node(
                node_id=request.node_id,
                name=request.name,
                gateway_id=request.gateway_id,
                position=request.position.to_domain() if request.position else None,
                available=request.available,
                battery_level=request.battery_level,
                transmission_range_m=request.transmission_range_m,
                data_source=request.data_source,
            )
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "node": node}

    @router.delete("/nodes/{node_id}")
    def delete_node(node_id: str) -> dict[str, Any]:
        try:
            node = simulator.remove_node(node_id)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "node": node}

    @router.post("/nodes/{node_id}/availability")
    def node_availability(
        node_id: str, request: AvailabilityUpdate
    ) -> dict[str, Any]:
        try:
            node = simulator.set_node_availability(node_id, request.available)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "node": node}

    @router.post("/nodes/{node_id}/gateway")
    def assign_gateway(
        node_id: str, request: GatewayAssignment
    ) -> dict[str, Any]:
        try:
            node = simulator.assign_gateway(node_id, request.gateway_id)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "node": node}

    @router.post("/gateways")
    def create_gateway(request: GatewayCreate) -> dict[str, Any]:
        try:
            gateway = simulator.create_gateway_node(
                gateway_id=request.gateway_id,
                name=request.name,
                position=request.position.to_domain() if request.position else None,
                available=request.available,
                transmission_range_m=request.transmission_range_m,
                storage_capacity_mb=request.storage_capacity_mb,
                storage_used_mb=request.storage_used_mb,
            )
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "gateway": gateway}

    @router.delete("/gateways/{gateway_id}")
    def delete_gateway(gateway_id: str) -> dict[str, Any]:
        try:
            gateway = simulator.remove_node(gateway_id)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "gateway": gateway}

    @router.post("/links")
    def create_link(request: LinkCreate) -> dict[str, Any]:
        try:
            link = simulator.create_link(
                source=request.source,
                destination=request.destination,
                link_id=request.link_id,
                quality=request.quality,
                etx=request.etx,
                latency_ms=request.latency_ms,
                packet_loss=request.packet_loss,
                available=request.available,
                bandwidth_kbps=request.bandwidth_kbps,
                bidirectional=request.bidirectional,
            )
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "link": link}

    @router.delete("/links/{link_id}")
    def delete_link(link_id: str) -> dict[str, Any]:
        try:
            link = simulator.remove_link(link_id)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "link": link}

    @router.post("/links/{link_id}/availability")
    def link_availability(
        link_id: str, request: AvailabilityUpdate
    ) -> dict[str, Any]:
        try:
            link = simulator.set_link_availability(link_id, request.available)
        except ValueError as exc:
            raise _failed(exc) from exc
        return {"ok": True, "link": link}

    return router


__all__ = ["create_network_router"]
