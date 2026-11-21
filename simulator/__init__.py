"""AirFed network simulator foundation.

The package is deliberately independent of the dashboard frontend and of the
federated-learning worker protocol.  It models a small wireless sensor network:
sensor nodes, gateways, configurable links, simulated sensor readings, and a
small engine that owns the current topology state.

Future stacks (RPL, Trickle, CoAP, MQTT gateway bridge) can be added on top of
the graph abstraction without changing the existing FL code.

Usage::

    from simulator.engine import NetworkSimulator

    engine = NetworkSimulator()
    engine.start()
    engine.advance(10)
    print(engine.snapshot())

Run a standalone CLI with ``python -m simulator``.
"""

from simulator.engine import NetworkSimulator, SimulationConfig
from simulator.entities import GatewayNode, SensorNode, SensorReading
from simulator.links import NetworkLink
from simulator.topology import NetworkTopology
from simulator.topology_config import (
    build_topology,
    default_topology_config,
    load_topology_config,
)

__all__ = [
    "GatewayNode",
    "NetworkLink",
    "NetworkSimulator",
    "NetworkTopology",
    "SensorNode",
    "SensorReading",
    "SimulationConfig",
    "build_topology",
    "default_topology_config",
    "load_topology_config",
]
