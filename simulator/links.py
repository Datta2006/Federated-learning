"""Link model for the simulated network graph.

Links are independent of nodes.  A link has its own quality, ETX, latency,
loss, availability, capacity, and direction flag.  These are inputs for a later
RPL stack; no route selection happens in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from simulator.entities import utc_now_iso


@dataclass
class NetworkLink:
    """A directed or bidirectional link between two network nodes."""

    link_id: str
    source: str
    destination: str
    quality: float = 1.0
    etx: float = 1.0
    latency_ms: float = 10.0
    packet_loss: float = 0.0
    available: bool = True
    bandwidth_kbps: float = 250.0
    bidirectional: bool = True
    last_updated: str = ""

    def __post_init__(self) -> None:
        if not self.last_updated:
            self.last_updated = utc_now_iso()

    def validate(self) -> None:
        """Validate link properties and endpoints."""
        if not self.link_id:
            raise ValueError("a link needs a link_id")
        if not self.source or not self.destination:
            raise ValueError("a link needs a source and destination")
        if self.source == self.destination:
            raise ValueError("a link cannot connect a node to itself")
        if not 0.0 <= float(self.quality) <= 1.0:
            raise ValueError("quality must be between 0 and 1")
        if float(self.etx) < 1.0:
            raise ValueError("etx must be at least 1")
        if float(self.latency_ms) < 0.0:
            raise ValueError("latency_ms must not be negative")
        if not 0.0 <= float(self.packet_loss) <= 1.0:
            raise ValueError("packet_loss must be between 0 and 1")
        if float(self.bandwidth_kbps) <= 0.0:
            raise ValueError("bandwidth_kbps must be positive")

    def endpoints(self) -> tuple[str, str]:
        return (self.source, self.destination)

    def touches(self, node_id: str) -> bool:
        return node_id in {self.source, self.destination}

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "source": self.source,
            "destination": self.destination,
            "quality": round(float(self.quality), 3),
            "etx": round(float(self.etx), 3),
            "latency_ms": round(float(self.latency_ms), 2),
            "packet_loss": round(float(self.packet_loss), 4),
            "available": bool(self.available),
            "bandwidth_kbps": round(float(self.bandwidth_kbps), 2),
            "bidirectional": bool(self.bidirectional),
            "direction": "bidirectional" if self.bidirectional else "directional",
            "last_updated": self.last_updated,
        }


__all__ = ["NetworkLink"]
