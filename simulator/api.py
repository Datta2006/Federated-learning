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
from simulator.rpl import DODAGConfiguration, DODAGMode, OCPOption, RPLMessageType


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

    # ------------------------------ RPL/Trickle endpoints
    @router.get("/rpl/state/{node_id}")
    def rpl_state(node_id: str) -> dict[str, Any]:
        """Get complete RPL state for a node (rank, parents, routes)."""
        return simulator.get_rpl_state(node_id)

    @router.get("/rpl/state")
    def all_rpl_state() -> dict[str, Any]:
        """Get RPL state for all nodes and DODAGs."""
        return simulator.get_all_rpl_state()

    @router.get("/rpl/dodag/{dodag_id}")
    def dodag_summary(dodag_id: str) -> dict[str, Any]:
        """Get summary of a DODAG."""
        return simulator.get_dodag_summary(dodag_id)

    @router.get("/rpl/route/{source}/{destination}")
    def rpl_route(source: str, destination: str) -> dict[str, Any]:
        """Compute RPL route between two nodes."""
        with simulator._lock:
            route = simulator.rpl_engine.compute_downward_route(source, destination)
            if route is None:
                # Try upward route
                for dodag_id in simulator.rpl_engine.dodag_configs:
                    upward = simulator.rpl_engine.compute_upward_route(source, dodag_id)
                    if destination in upward:
                        return {"route": upward[:upward.index(destination)+1], "type": "upward"}
            if route:
                return {"route": route, "type": "downward"}
            return {"route": [], "type": "none", "error": "No route found"}

    @router.get("/trickle/state/{node_id}/{dodag_id}")
    def trickle_state(node_id: str, dodag_id: str) -> dict[str, Any]:
        """Get Trickle timer state for a node/DODAG."""
        state = simulator.get_trickle_state(node_id, dodag_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Trickle timer not found")
        return state

    @router.get("/trickle/state")
    def all_trickle_state() -> dict[str, Any]:
        """Get Trickle state for all nodes."""
        return simulator.get_all_trickle_state()

    @router.post("/rpl/dodag")
    def create_dodag(request: dict[str, Any]) -> dict[str, Any]:
        """Create a new DODAG rooted at a gateway."""
        gateway_id = request.get("gateway_id")
        instance_id = request.get("instance_id", 0)
        dodag_id = request.get("dodag_id")
        if not gateway_id:
            raise HTTPException(status_code=400, detail="gateway_id required")
        try:
            config = simulator.rpl_engine.initialize_dodag(gateway_id, instance_id, dodag_id)
            simulator._init_trickle_for_node(gateway_id, config.dodag_id)
            return {"ok": True, "config": config.__dict__}
        except ValueError as exc:
            raise _failed(exc) from exc

    @router.post("/rpl/join/{node_id}")
    def join_dodag(node_id: str, request: dict[str, Any]) -> dict[str, Any]:
        """Trigger a node to join a DODAG (send DIS)."""
        dodag_id = request.get("dodag_id")
        if not dodag_id:
            raise HTTPException(status_code=400, detail="dodag_id required")
        with simulator._lock:
            state = simulator.rpl_engine.get_or_create_node_state(node_id)
            if dodag_id not in simulator._trickle_timers.get(node_id, {}):
                simulator._init_trickle_for_node(node_id, dodag_id)
            # Reset Trickle to send DIS immediately
            timer = simulator._trickle_timers[node_id][dodag_id]
            timer.reset(0.0)
            return {"ok": True, "node_id": node_id, "dodag_id": dodag_id}

    return router


__all__ = ["create_network_router"]
