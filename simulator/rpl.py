"""RPL (Routing Protocol for Low-Power and Lossy Networks) implementation.

Based on RFC 6550. Implements:
- DODAG (Destination-Oriented Directed Acyclic Graph) per gateway
- Rank calculation with ETX objective function
- Parent selection (preferred parent + candidate parents)
- DIO/DIS/DAO message handling
- Routing tables with downward reachability
- Multi-hop route computation
- Loop prevention (rank monotonicity)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from simulator.entities import NetworkNode, SensorNode
from simulator.topology import NetworkTopology


class RPLMessageType(Enum):
    """RPL control message types."""

    DIO = "dio"  # DODAG Information Object
    DIS = "dis"  # DODAG Information Solicitation
    DAO = "dao"  # Destination Advertisement Object
    DAO_ACK = "dao_ack"  # DAO Acknowledgment


class DODAGMode(Enum):
    """DODAG mode of operation (RFC 6550 Section 8.2)."""

    NO_DOWNWARD_ROUTES = 0
    NON_STORING = 1
    STORING = 2
    STORING_WITH_MCAST = 3


class OCPOption(Enum):
    """Objective Code Point for Objective Function (RFC 6552)."""

    ETX = 1  # Expected Transmission Count (RFC 6552)
    MRHOF = 2  # Minimum Rank with Hysteresis Objective Function


@dataclass
class DODAGConfiguration:
    """DODAG configuration parameters (RFC 6550 Section 8.2)."""

    dodag_id: str  # DODAG identifier (typically IPv6 address of root)
    instance_id: int = 0  # RPL Instance ID
    mode: DODAGMode = DODAGMode.STORING
    ocp: OCPOption = OCPOption.ETX
    default_route_injected: bool = False
    dag_max_rank_increase: int = 2048  # DAGMaxRankIncrease
    min_hop_rank_increase: int = 256  # MinHopRankIncrease
    max_rank: int = 0xFFFF  # MAX_RANK


@dataclass
class DIOMessage:
    """DODAG Information Object (RFC 6550 Section 8.3)."""

    message_type: RPLMessageType = RPLMessageType.DIO
    dodag_id: str = ""
    instance_id: int = 0
    version: int = 0
    rank: int = 0xFFFF
    dag_int_doubling: int = 16  # DIOIntervalDoublings
    dag_int_min: int = 1  # DIOIntervalMin (log2 seconds)
    dag_int_current: int = 1  # Current interval
    ocp: OCPOption = OCPOption.ETX
    reserved: int = 0
    mop: int = 2  # Mode of Operation (STORING)
    prf: int = 0  # Preference
    dtsn: int = 0  # Destination Sequence Number
    flags: int = 0
    # Suboptions would go here (prefix, target, etc.)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.message_type.value,
            "dodag_id": self.dodag_id,
            "instance_id": self.instance_id,
            "version": self.version,
            "rank": self.rank,
            "dag_int_doubling": self.dag_int_doubling,
            "dag_int_min": self.dag_int_min,
            "dag_int_current": self.dag_int_current,
            "ocp": self.ocp.value,
            "mop": self.mop,
            "prf": self.prf,
            "dtsn": self.dtsn,
            "flags": self.flags,
        }


@dataclass
class DISMessage:
    """DODAG Information Solicitation (RFC 6550 Section 8.4)."""

    message_type: RPLMessageType = RPLMessageType.DIS
    instance_id: int = 0
    dodag_id: str = ""  # Optional, if omitted solicits all
    flags: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.message_type.value,
            "instance_id": self.instance_id,
            "dodag_id": self.dodag_id,
            "flags": self.flags,
        }


@dataclass
class DAOMessage:
    """Destination Advertisement Object (RFC 6550 Section 9)."""

    message_type: RPLMessageType = RPLMessageType.DAO
    instance_id: int = 0
    dodag_id: str = ""
    flags: int = 0  # K (ACK requested), D (DAO-ACK)
    dao_sequence: int = 0
    targets: list[str] = field(default_factory=list)  # Target prefixes/addresses
    transit_info: list[dict[str, Any]] = field(default_factory=list)  # Path info

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.message_type.value,
            "instance_id": self.instance_id,
            "dodag_id": self.dodag_id,
            "flags": self.flags,
            "dao_sequence": self.dao_sequence,
            "targets": self.targets,
            "transit_info": self.transit_info,
        }


@dataclass
class ParentCandidate:
    """Candidate parent with metrics for parent selection."""

    node_id: str
    rank: int
    etx: float
    link_quality: float
    path_etx: float  # Cumulative ETX to root through this parent
    is_preferred: bool = False
    last_dio_time: float = 0.0
    dio_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "rank": self.rank,
            "etx": self.etx,
            "link_quality": self.link_quality,
            "path_etx": self.path_etx,
            "is_preferred": self.is_preferred,
            "last_dio_time": self.last_dio_time,
            "dio_count": self.dio_count,
        }


@dataclass
class NodeRank:
    """Rank information for a node in a DODAG."""

    node_id: str
    dodag_id: str
    rank: int = 0xFFFF  # INFINITE_RANK
    min_rank: int = 0xFFFF
    preferred_parent: str | None = None
    candidate_parents: list[ParentCandidate] = field(default_factory=list)
    rank_updated_time: float = 0.0
    rank_changes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "dodag_id": self.dodag_id,
            "rank": self.rank,
            "min_rank": self.min_rank,
            "preferred_parent": self.preferred_parent,
            "candidate_parents": [p.to_dict() for p in self.candidate_parents],
            "rank_updated_time": self.rank_updated_time,
            "rank_changes": self.rank_changes,
        }


@dataclass
class RoutingTableEntry:
    """Routing table entry for downward routing (RFC 6550 Section 11)."""

    destination: str  # Target node/prefix
    next_hop: str  # Next hop toward destination
    interface: str = ""  # Interface (for multi-interface nodes)
    path_sequence: int = 0
    lifetime: float = 0.0  # Remaining lifetime
    learned_from: str = ""  # Node that advertised this route
    rank: int = 0  # Rank of the destination
    is_downward: bool = True  # True for downward, False for upward

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "next_hop": self.next_hop,
            "interface": self.interface,
            "path_sequence": self.path_sequence,
            "lifetime": self.lifetime,
            "learned_from": self.learned_from,
            "rank": self.rank,
            "is_downward": self.is_downward,
        }


@dataclass
class RPLNodeState:
    """Complete RPL state for a single node."""

    node_id: str
    dodag_id: str = ""
    instance_id: int = 0
    is_root: bool = False
    rank: NodeRank | None = None
    routing_table: list[RoutingTableEntry] = field(default_factory=list)
    dio_sequence: int = 0
    dao_sequence: int = 0
    joined_dodag: bool = False
    joined_time: float = 0.0
    parent_switch_count: int = 0
    last_dio_sent: float = 0.0
    last_dao_sent: float = 0.0
    dis_sent_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "dodag_id": self.dodag_id,
            "instance_id": self.instance_id,
            "is_root": self.is_root,
            "rank": self.rank.to_dict() if self.rank else None,
            "routing_table": [e.to_dict() for e in self.routing_table],
            "dio_sequence": self.dio_sequence,
            "dao_sequence": self.dao_sequence,
            "joined_dodag": self.joined_dodag,
            "joined_time": self.joined_time,
            "parent_switch_count": self.parent_switch_count,
            "last_dio_sent": self.last_dio_sent,
            "last_dao_sent": self.last_dao_sent,
            "dis_sent_count": self.dis_sent_count,
        }


class RPLEngine:
    """Main RPL protocol engine managing DODAGs and routing."""

    def __init__(self, topology: NetworkTopology, seed: int = 42) -> None:
        self.topology = topology
        self.rng = random.Random(seed)
        self.nodes_state: dict[str, RPLNodeState] = {}
        self.dodag_configs: dict[str, DODAGConfiguration] = {}
        self._rank_counter = 0

    def initialize_dodag(
        self, gateway_id: str, instance_id: int = 0, dodag_id: str | None = None
    ) -> DODAGConfiguration:
        """Initialize a DODAG rooted at a gateway."""
        gateway = self.topology.get_gateway(gateway_id)
        if not gateway:
            raise ValueError(f"Gateway {gateway_id} not found")

        dodag_id = dodag_id or f"fd00::{gateway_id.replace('-', ':').lower()}"
        config = DODAGConfiguration(
            dodag_id=dodag_id,
            instance_id=instance_id,
            mode=DODAGMode.STORING,
            ocp=OCPOption.ETX,
        )
        self.dodag_configs[dodag_id] = config

        # Initialize root state
        state = RPLNodeState(
            node_id=gateway_id,
            dodag_id=dodag_id,
            instance_id=instance_id,
            is_root=True,
            joined_dodag=True,
            joined_time=0.0,
        )
        state.rank = NodeRank(
            node_id=gateway_id,
            dodag_id=dodag_id,
            rank=config.min_hop_rank_increase,  # ROOT rank = MinHopRankIncrease
            min_rank=config.min_hop_rank_increase,
            rank_updated_time=0.0,
        )
        self.nodes_state[gateway_id] = state
        return config

    def get_or_create_node_state(self, node_id: str) -> RPLNodeState:
        """Get or create RPL state for a node."""
        if node_id not in self.nodes_state:
            self.nodes_state[node_id] = RPLNodeState(node_id=node_id)
        return self.nodes_state[node_id]

    def compute_rank(
        self, node_id: str, parent_id: str, link_etx: float, config: DODAGConfiguration
    ) -> int:
        """Compute rank for a node based on parent rank and link ETX.

        Rank = parent_rank + MinHopRankIncrease * ETX
        Per RFC 6550 Section 8.2.2 and RFC 6552.
        """
        parent_state = self.nodes_state.get(parent_id)
        if not parent_state or not parent_state.rank:
            return 0xFFFF  # INFINITE_RANK

        parent_rank = parent_state.rank.rank
        rank_increase = int(config.min_hop_rank_increase * link_etx)
        new_rank = parent_rank + rank_increase

        # Enforce rank limits
        max_rank = config.max_rank
        if new_rank > max_rank:
            new_rank = max_rank

        # Check DAGMaxRankIncrease constraint
        if parent_rank + config.dag_max_rank_increase < new_rank:
            new_rank = parent_rank + config.dag_max_rank_increase

        return new_rank

    def compute_path_etx(self, node_id: str, parent_id: str, link_etx: float) -> float:
        """Compute cumulative path ETX to root through a parent."""
        parent_state = self.nodes_state.get(parent_id)
        if not parent_state or not parent_state.rank:
            return float("inf")

        # Find parent's path ETX (via its preferred parent)
        parent_path_etx = 0.0
        if parent_state.rank.preferred_parent:
            for candidate in parent_state.rank.candidate_parents:
                if candidate.node_id == parent_state.rank.preferred_parent:
                    parent_path_etx = candidate.path_etx
                    break
        else:
            # Parent is root
            parent_path_etx = 0.0

        return parent_path_etx + link_etx

    def update_candidate_parents(
        self, node_id: str, dodag_id: str, now: float
    ) -> list[ParentCandidate]:
        """Update candidate parents for a node based on received DIOs."""
        node = self.topology.get_node(node_id)
        if not node:
            return []

        config = self.dodag_configs.get(dodag_id)
        if not config:
            return []

        state = self.get_or_create_node_state(node_id)
        state.dodag_id = dodag_id
        state.instance_id = config.instance_id

        candidates = []
        neighbors = self.topology.neighbors(node_id)

        for neighbor_id in neighbors:
            neighbor_state = self.nodes_state.get(neighbor_id)
            if not neighbor_state or not neighbor_state.rank:
                continue

            # Check if neighbor is in same DODAG
            if neighbor_state.dodag_id != dodag_id:
                continue

            # Get link ETX
            link = self.topology.get_link_between(node_id, neighbor_id)
            if not link or not link.available:
                continue

            # Neighbor must have finite rank (not INFINITE_RANK)
            if neighbor_state.rank.rank >= 0xFFFF:
                continue

            # Loop prevention: neighbor rank must be less than our potential rank
            neighbor_rank = neighbor_state.rank.rank
            path_etx = self.compute_path_etx(node_id, neighbor_id, link.etx)
            potential_rank = self.compute_rank(node_id, neighbor_id, link.etx, config)

            # Rank must be strictly greater than neighbor's rank (monotonicity)
            if potential_rank <= neighbor_rank:
                continue

            # Additional loop check: rank must not decrease
            if state.rank and potential_rank < state.rank.rank:
                # Only allow if significantly better (hysteresis)
                if potential_rank >= state.rank.rank - 128:
                    continue

            candidate = ParentCandidate(
                node_id=neighbor_id,
                rank=neighbor_rank,
                etx=link.etx,
                link_quality=link.quality,
                path_etx=path_etx,
            )
            candidates.append(candidate)

        # Sort by path ETX (primary), then by rank, then by link quality
        candidates.sort(key=lambda c: (c.path_etx, c.rank, -c.link_quality))

        return candidates

    def select_preferred_parent(self, candidates: list[ParentCandidate]) -> ParentCandidate | None:
        """Select preferred parent from candidates using RFC 6552 OF0 (ETX)."""
        if not candidates:
            return None

        # OF0: Minimum Rank with Hysteresis Objective Function
        # Primary: lowest path ETX
        # Hysteresis: don't switch unless significantly better
        best = candidates[0]
        best.is_preferred = True

        # Apply hysteresis (RFC 6552 Section 4.2)
        # Don't switch parent unless new path_etx is significantly better
        # (typically 10% better or fixed threshold)
        for candidate in candidates:
            if candidate is best:
                continue
            # If another candidate has much better path ETX, consider it
            if candidate.path_etx < best.path_etx * 0.9:
                best.is_preferred = False
                candidate.is_preferred = True
                best = candidate
                break

        return best

    def update_node_rank(self, node_id: str, dodag_id: str, now: float) -> bool:
        """Update node's rank based on candidate parents. Returns True if rank changed."""
        state = self.get_or_create_node_state(node_id)
        candidates = self.update_candidate_parents(node_id, dodag_id, now)
        preferred = self.select_preferred_parent(candidates)

        old_rank = state.rank.rank if state.rank else 0xFFFF
        old_preferred = state.rank.preferred_parent if state.rank else None

        if not preferred:
            # No valid parent - rank becomes INFINITE_RANK
            if state.rank:
                state.rank.rank = 0xFFFF
                state.rank.preferred_parent = None
                state.rank.candidate_parents = candidates
                state.rank.rank_updated_time = now
            else:
                state.rank = NodeRank(
                    node_id=node_id,
                    dodag_id=dodag_id,
                    rank=0xFFFF,
                    candidate_parents=candidates,
                    rank_updated_time=now,
                )
            return old_rank != 0xFFFF

        # Compute new rank
        config = self.dodag_configs[dodag_id]
        new_rank = self.compute_rank(node_id, preferred.node_id, preferred.etx, config)

        rank_changed = False
        parent_changed = False

        if state.rank:
            if new_rank != state.rank.rank:
                rank_changed = True
                state.rank.rank = new_rank
                state.rank.rank_changes += 1
            if preferred.node_id != state.rank.preferred_parent:
                parent_changed = True
                state.rank.preferred_parent = preferred.node_id
                state.parent_switch_count += 1

            state.rank.candidate_parents = candidates
            state.rank.rank_updated_time = now
            state.rank.min_rank = min(state.rank.min_rank, new_rank)
        else:
            state.rank = NodeRank(
                node_id=node_id,
                dodag_id=dodag_id,
                rank=new_rank,
                min_rank=new_rank,
                preferred_parent=preferred.node_id,
                candidate_parents=candidates,
                rank_updated_time=now,
            )
            rank_changed = True
            parent_changed = True

        if parent_changed and state.joined_dodag:
            # Need to send DAO to new parent
            pass  # Handled in DAO logic

        return rank_changed or parent_changed

    def compute_upward_route(self, node_id: str, dodag_id: str) -> list[str]:
        """Compute the upward route from node to DODAG root."""
        route = [node_id]
        current = node_id
        visited = set()

        while current:
            if current in visited:
                # Loop detected
                return []
            visited.add(current)

            state = self.nodes_state.get(current)
            if not state or not state.rank or not state.rank.preferred_parent:
                break

            parent = state.rank.preferred_parent
            route.append(parent)

            if state.is_root:
                break

            current = parent

        return route

    def compute_downward_route(self, source: str, destination: str) -> list[str] | None:
        """Compute downward route from source to destination using routing tables."""
        # For storing mode: look up destination in routing table
        state = self.nodes_state.get(source)
        if not state:
            return None

        for entry in state.routing_table:
            if entry.destination == destination:
                # Follow next hops
                route = [source]
                current = entry.next_hop
                while current != destination:
                    route.append(current)
                    next_state = self.nodes_state.get(current)
                    if not next_state:
                        return None
                    # Find next hop toward destination
                    found = False
                    for e in next_state.routing_table:
                        if e.destination == destination:
                            current = e.next_hop
                            found = True
                            break
                    if not found:
                        return None
                route.append(destination)
                return route

        return None

    def add_routing_entry(
        self,
        node_id: str,
        destination: str,
        next_hop: str,
        rank: int,
        learned_from: str,
        lifetime: float = 3600.0,
    ) -> None:
        """Add or update a routing table entry."""
        state = self.get_or_create_node_state(node_id)

        # Check if entry exists
        for entry in state.routing_table:
            if entry.destination == destination:
                entry.next_hop = next_hop
                entry.rank = rank
                entry.learned_from = learned_from
                entry.lifetime = lifetime
                entry.path_sequence += 1
                return

        # New entry
        state.routing_table.append(
            RoutingTableEntry(
                destination=destination,
                next_hop=next_hop,
                rank=rank,
                learned_from=learned_from,
                lifetime=lifetime,
            )
        )

    def process_dio(
        self, source_id: str, dio: DIOMessage, now: float
    ) -> list[DIOMessage]:
        """Process received DIO, return any triggered DIOs."""
        source_state = self.nodes_state.get(source_id)
        if not source_state:
            return []

        # Verify DODAG match
        if dio.dodag_id not in self.dodag_configs:
            return []

        config = self.dodag_configs[dio.dodag_id]

        # Update source node state from DIO
        source_state.dodag_id = dio.dodag_id
        source_state.instance_id = dio.instance_id

        if not source_state.rank:
            source_state.rank = NodeRank(
                node_id=source_id,
                dodag_id=dio.dodag_id,
                rank=dio.rank,
            )
        else:
            source_state.rank.rank = dio.rank
            source_state.rank.rank_updated_time = now

        triggered = []

        # Propagate to neighbors (simulate DIO forwarding)
        neighbors = self.topology.neighbors(source_id)
        for neighbor_id in neighbors:
            neighbor_state = self.nodes_state.get(neighbor_id)
            if not neighbor_id or neighbor_id == source_id:
                continue

            # Check if neighbor should update rank
            self.update_node_rank(neighbor_id, dio.dodag_id, now)

        return triggered

    def process_dis(self, source_id: str, dis: DISMessage, now: float) -> list[DIOMessage]:
        """Process DIS, return solicited DIOs."""
        triggered = []

        # If DIS specifies a DODAG, only that DODAG responds
        # Otherwise all DODAGs respond
        target_dodags = []
        if dis.dodag_id:
            if dis.dodag_id in self.dodag_configs:
                target_dodags = [dis.dodag_id]
        else:
            target_dodags = list(self.dodag_configs.keys())

        for dodag_id in target_dodags:
            config = self.dodag_configs[dodag_id]
            root_state = None
            for state in self.nodes_state.values():
                if state.is_root and state.dodag_id == dodag_id:
                    root_state = state
                    break

            if root_state and root_state.rank:
                dio = DIOMessage(
                    dodag_id=dodag_id,
                    instance_id=config.instance_id,
                    version=root_state.dio_sequence,
                    rank=root_state.rank.rank,
                    ocp=config.ocp,
                    mop=config.mode.value,
                )
                triggered.append(dio)

        return triggered

    def process_dao(self, source_id: str, dao: DAOMessage, now: float) -> DAOMessage | None:
        """Process DAO, update routing tables, return DAO-ACK if requested."""
        source_state = self.nodes_state.get(source_id)
        if not source_state or not source_state.rank:
            return None

        # Verify DODAG
        if dao.dodag_id != source_state.dodag_id:
            return None

        # For storing mode: install downward routes
        config = self.dodag_configs.get(dao.dodag_id)
        if not config or config.mode == DODAGMode.NO_DOWNWARD_ROUTES:
            return None

        # Add routing entries for each target
        for target in dao.targets:
            # The DAO comes from source_id, so next_hop toward target is source_id
            # The node receiving this DAO should forward it toward root
            current = source_id
            while current:
                current_state = self.nodes_state.get(current)
                if not current_state:
                    break

                # Add route to target via source_id (which is downstream)
                # Actually in storing mode, each node adds route to target via the node
                # that sent the DAO (which is closer to target)
                self.add_routing_entry(
                    node_id=current,
                    destination=target,
                    next_hop=source_id if current != source_id else target,
                    rank=source_state.rank.rank if source_state.rank else 0,
                    learned_from=source_id,
                )

                if current_state.is_root:
                    break

                if not current_state.rank or not current_state.rank.preferred_parent:
                    break
                current = current_state.rank.preferred_parent

        # Generate DAO-ACK if requested (K flag)
        if dao.flags & 0x80:  # K flag = ACK requested
            ack = DAOMessage(
                message_type=RPLMessageType.DAO_ACK,
                instance_id=dao.instance_id,
                dodag_id=dao.dodag_id,
                flags=0,
                dao_sequence=dao.dao_sequence,
            )
            return ack

        return None

    def get_node_rpl_state(self, node_id: str) -> dict[str, Any]:
        """Get complete RPL state for a node for API/visualization."""
        state = self.nodes_state.get(node_id)
        if not state:
            return {"error": "Node not found in RPL"}

        result = state.to_dict()

        # Add computed routes
        if state.dodag_id and state.rank:
            result["upward_route"] = self.compute_upward_route(node_id, state.dodag_id)

            # Find all reachable destinations (downward)
            destinations = []
            for entry in state.routing_table:
                if entry.is_downward:
                    route = self.compute_downward_route(node_id, entry.destination)
                    if route:
                        destinations.append(
                            {"destination": entry.destination, "route": route, "next_hop": entry.next_hop}
                        )
            result["downward_routes"] = destinations

        return result

    def get_dodag_summary(self, dodag_id: str) -> dict[str, Any]:
        """Get summary of a DODAG."""
        config = self.dodag_configs.get(dodag_id)
        if not config:
            return {"error": "DODAG not found"}

        nodes_in_dodag = [
            (nid, state)
            for nid, state in self.nodes_state.items()
            if state.dodag_id == dodag_id
        ]

        return {
            "dodag_id": dodag_id,
            "instance_id": config.instance_id,
            "mode": config.mode.name,
            "ocp": config.ocp.name,
            "root": next((nid for nid, s in nodes_in_dodag if s.is_root), None),
            "node_count": len(nodes_in_dodag),
            "nodes": {
                nid: {
                    "rank": state.rank.rank if state.rank else None,
                    "preferred_parent": state.rank.preferred_parent if state.rank else None,
                    "candidate_count": len(state.rank.candidate_parents) if state.rank else 0,
                    "joined": state.joined_dodag,
                }
                for nid, state in nodes_in_dodag
            },
        }

    def step(self, now: float) -> dict[str, list[Any]]:
        """Perform one simulation step - process Trickle timers, send DIOs, DAOs."""
        # This will be called by the simulation engine
        # Returns messages to send: {"dio": [...], "dis": [...], "dao": [...]}
        return {"dio": [], "dis": [], "dao": []}


def create_rpl_engine(topology: NetworkTopology, seed: int = 42) -> RPLEngine:
    """Factory function to create RPL engine."""
    return RPLEngine(topology, seed)