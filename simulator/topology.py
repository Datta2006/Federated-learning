"""Graph representation of the simulated network.

The topology owns nodes and links.  It knows about adjacency, path finding and
gateway membership, but it knows nothing about readings, HTTP, or routing
protocols.  A later RPL stack can use :meth:`neighbors` and :meth:`find_paths`
as inputs without changing this layer.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any

from simulator.entities import GatewayNode, NetworkNode, SensorNode
from simulator.links import NetworkLink


class NetworkTopology:
    """Mutable graph of sensor nodes, gateways, and links."""

    def __init__(self, name: str = "AirFed simulated network") -> None:
        self.name = name
        self.description = ""
        self.nodes: dict[str, NetworkNode] = {}
        self.links: dict[str, NetworkLink] = {}

    # --------------------------------------------------------------- nodes
    def add_node(self, node: NetworkNode) -> NetworkNode:
        node_id = self._node_id(node)
        if not node_id:
            raise ValueError("a network node needs an id")
        if node_id in self.nodes:
            raise ValueError(f"node {node_id!r} already exists")
        if isinstance(node, SensorNode) and node.gateway_id is not None:
            gateway = self.nodes.get(node.gateway_id)
            if not isinstance(gateway, GatewayNode):
                raise ValueError(
                    f"assigned gateway {node.gateway_id!r} does not exist"
                )
        self.nodes[node_id] = node
        self._refresh_derived_state()
        return node

    def add_sensor_node(self, node: SensorNode) -> SensorNode:
        return self.add_node(node)

    def add_gateway_node(self, node: GatewayNode) -> GatewayNode:
        return self.add_node(node)

    def get_node(self, node_id: str) -> NetworkNode:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise ValueError(f"unknown node {node_id!r}") from exc

    def get_sensor(self, node_id: str) -> SensorNode:
        node = self.get_node(node_id)
        if not isinstance(node, SensorNode):
            raise ValueError(f"node {node_id!r} is not a sensor")  # noqa: TRY004
        return node

    def get_gateway(self, node_id: str) -> GatewayNode:
        node = self.get_node(node_id)
        if not isinstance(node, GatewayNode):
            raise ValueError(f"node {node_id!r} is not a gateway")  # noqa: TRY004
        return node

    def remove_node(self, node_id: str) -> NetworkNode:
        node = self.get_node(node_id)
        for link_id in [
            link.link_id
            for link in self.links.values()
            if link.touches(node_id)
        ]:
            del self.links[link_id]
        del self.nodes[node_id]
        if isinstance(node, GatewayNode):
            for candidate in self.nodes.values():
                if isinstance(candidate, SensorNode) and candidate.gateway_id == node_id:
                    candidate.gateway_id = None
        self._refresh_derived_state()
        return node

    def assign_sensor(self, sensor_id: str, gateway_id: str | None) -> SensorNode:
        sensor = self.get_sensor(sensor_id)
        if gateway_id is not None:
            self.get_gateway(gateway_id)
        sensor.gateway_id = gateway_id
        self._refresh_derived_state()
        return sensor

    def sensors_assigned_to(self, gateway_id: str) -> list[SensorNode]:
        self.get_gateway(gateway_id)
        return [
            node
            for node in self.nodes.values()
            if isinstance(node, SensorNode) and node.gateway_id == gateway_id
        ]

    # --------------------------------------------------------------- links
    def add_link(self, link: NetworkLink) -> NetworkLink:
        link.validate()
        if link.link_id in self.links:
            raise ValueError(f"link {link.link_id!r} already exists")
        if link.source not in self.nodes:
            raise ValueError(f"link source {link.source!r} does not exist")
        if link.destination not in self.nodes:
            raise ValueError(
                f"link destination {link.destination!r} does not exist"
            )
        self.links[link.link_id] = link
        self._refresh_derived_state()
        return link

    def get_link(self, link_id: str) -> NetworkLink:
        try:
            return self.links[link_id]
        except KeyError as exc:
            raise ValueError(f"unknown link {link_id!r}") from exc

    def remove_link(self, link_id: str) -> NetworkLink:
        link = self.get_link(link_id)
        del self.links[link_id]
        self._refresh_derived_state()
        return link

    def update_link(self, link_id: str, **changes: Any) -> NetworkLink:
        link = self.get_link(link_id)
        for key, value in changes.items():
            if not hasattr(link, key):
                raise ValueError(f"unknown link property {key!r}")
            setattr(link, key, value)
        link.validate()
        self._refresh_derived_state()
        return link

    def links_for(self, node_id: str) -> list[NetworkLink]:
        self.get_node(node_id)
        return [link for link in self.links.values() if link.touches(node_id)]

    def get_link_between(self, node_a: str, node_b: str) -> NetworkLink | None:
        """Get the link between two nodes, regardless of direction."""
        self.get_node(node_a)
        self.get_node(node_b)
        for link in self.links.values():
            if (link.source == node_a and link.destination == node_b) or (
                link.bidirectional and link.source == node_b and link.destination == node_a
            ):
                return link
        return None

    # ------------------------------------------------------------- topology
    def neighbors(self, node_id: str, available_only: bool = False) -> list[str]:
        self.get_node(node_id)
        result: list[str] = []
        for link in self.links.values():
            if available_only and not link.available:
                continue
            if link.source == node_id:
                result.append(link.destination)
            if link.bidirectional and link.destination == node_id:
                result.append(link.source)
        return sorted(set(result))

    def find_paths(
        self,
        source: str,
        destination: str,
        *,
        max_paths: int = 8,
        available_only: bool = True,
        max_length: int | None = None,
    ) -> list[list[str]]:
        """Return simple paths between two nodes.

        This is a generic graph helper for tests and future route computation.
        It is **not** an RPL implementation and does not select a parent.
        """
        self.get_node(source)
        self.get_node(destination)
        if source == destination:
            return [[source]]
        limit = max_length or len(self.nodes)
        paths: list[list[str]] = []

        def walk(node: str, path: list[str]) -> None:
            if len(paths) >= max_paths or len(path) > limit:
                return
            if node == destination:
                paths.append(path)
                return
            for neighbor in self.neighbors(node, available_only=available_only):
                if neighbor in path:
                    continue
                walk(neighbor, [*path, neighbor])

        walk(source, [source])
        return paths

    def shortest_path(
        self, source: str, destination: str, *, available_only: bool = True
    ) -> list[str] | None:
        self.get_node(source)
        self.get_node(destination)
        queue: deque[list[str]] = deque([[source]])
        seen = {source}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == destination:
                return path
            for neighbor in self.neighbors(node, available_only=available_only):
                if neighbor in seen:
                    continue
                seen.add(neighbor)
                queue.append([*path, neighbor])
        return None

    def is_connected(self, source: str, destination: str) -> bool:
        return self.shortest_path(source, destination) is not None

    # -------------------------------------------------------------- helpers
    @staticmethod
    def _node_id(node: NetworkNode) -> str:
        if isinstance(node, GatewayNode):
            return node.gateway_id
        return node.node_id

    def _refresh_derived_state(self) -> None:
        for node in self.nodes.values():
            node.neighbors = self.neighbors(self._node_id(node))
        for node in self.nodes.values():
            if isinstance(node, GatewayNode):
                node.connected_sensor_count = sum(
                    1
                    for sensor in self.nodes.values()
                    if isinstance(sensor, SensorNode)
                    and sensor.gateway_id == node.gateway_id
                )

    def sensor_nodes(self) -> Iterable[SensorNode]:
        return (node for node in self.nodes.values() if isinstance(node, SensorNode))

    def gateway_nodes(self) -> Iterable[GatewayNode]:
        return (
            node for node in self.nodes.values() if isinstance(node, GatewayNode)
        )

    def snapshot(self) -> dict[str, Any]:
        sensors = list(self.sensor_nodes())
        gateways = list(self.gateway_nodes())
        return {
            "name": self.name,
            "description": self.description,
            "counts": {
                "nodes": len(self.nodes),
                "sensors": len(sensors),
                "gateways": len(gateways),
                "links": len(self.links),
                "online_sensors": sum(1 for node in sensors if node.available),
                "online_gateways": sum(1 for node in gateways if node.available),
                "available_links": sum(
                    1 for link in self.links.values() if link.available
                ),
            },
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "sensors": [node.to_dict() for node in sensors],
            "gateways": [node.to_dict() for node in gateways],
            "links": [link.to_dict() for link in self.links.values()],
            "gateway_assignments": {
                gateway.gateway_id: [
                    sensor.node_id
                    for sensor in self.sensors_assigned_to(gateway.gateway_id)
                ]
                for gateway in gateways
            },
        }


__all__ = ["NetworkTopology"]
