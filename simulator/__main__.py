"""Standalone CLI for inspecting the network simulator.

The dashboard API is the normal control surface.  This module exists so the
foundation can be exercised without starting FastAPI::

    python -m simulator --start --advance 30
    python -m simulator --topology path/to/topology.json
"""

from __future__ import annotations

import argparse
import json

from simulator.engine import NetworkSimulator
from simulator.topology_config import load_topology_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the AirFed network simulator")
    parser.add_argument("--topology", help="optional topology JSON file")
    parser.add_argument(
        "--start", action="store_true", help="start the simulation before advancing"
    )
    parser.add_argument(
        "--advance",
        type=float,
        default=0.0,
        help="simulated seconds to advance before printing",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print counts and status only, not every node and link",
    )
    args = parser.parse_args()

    config = load_topology_config(args.topology) if args.topology else None
    simulator = NetworkSimulator(config)
    if args.start:
        simulator.start()
    if args.advance:
        simulator.advance(args.advance)

    payload = simulator.status_payload() if args.summary else simulator.snapshot()
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
