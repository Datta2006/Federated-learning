"""Stable, collision-safe identity mapping for gateway federated clients.

A simulator gateway is not a federated worker by default.  When it becomes one
(Approach 2), it needs a worker id that the existing FL protocol accepts
(``[A-Za-z0-9_.:-]+``) and that can never collide with another gateway or with
the configured ``node1..node5`` workers.

The mapping is deterministic for a given gateway id: the readable slug plus a
truncated SHA-256 digest.  A small in-memory registry additionally guards
against the (astronomical) case where two different ids truncate to the same
digest: the later claimant gets a longer digest until the id is unique.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Matches common.worker_protocol._SAFE_TOKEN, but we restrict to characters that
# are also pleasant in a dashboard and in a filesystem path.
_SLUG_RE = re.compile(r"[^a-z0-9_-]+")
DEFAULT_PREFIX = "gw"
_MAX_SLUG = 24


def sanitize_component(value: str) -> str:
    """Return a filesystem/topic safe lowercase component."""
    slug = _SLUG_RE.sub("-", str(value).strip().lower()).strip("-_")
    return slug[:_MAX_SLUG].strip("-_") or "gateway"


def _digest(value: str, length: int) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def candidate_worker_id(
    gateway_id: str, *, prefix: str = DEFAULT_PREFIX, digest_length: int = 10
) -> str:
    """Build a worker id for ``gateway_id`` with an explicit digest length.

    The result is always a valid FL worker token (no ``/``, ``+`` or ``#``) and
    is bounded to a comfortable MQTT topic length.
    """
    if not 6 <= digest_length <= 64:
        raise ValueError("digest_length must be between 6 and 64")
    slug = sanitize_component(gateway_id)
    safe_prefix = sanitize_component(prefix) or DEFAULT_PREFIX
    return f"{safe_prefix}-{slug}-{_digest(str(gateway_id), digest_length)}"


@dataclass(frozen=True)
class GatewayIdentity:
    """One frozen gateway -> worker mapping."""

    gateway_id: str
    worker_id: str
    digest_length: int


class GatewayIdentityRegistry:
    """Allocate and remember collision-safe worker ids for gateways.

    The registry is intentionally process-local and is meant to live as long as
    the simulator engine.  ``assign`` is idempotent: the same gateway always
    gets the same worker id for the lifetime of the registry.
    """

    def __init__(self, *, prefix: str = DEFAULT_PREFIX) -> None:
        self.prefix = prefix
        self._by_gateway: dict[str, GatewayIdentity] = {}
        self._by_worker: dict[str, str] = {}

    def assign(self, gateway_id: str) -> GatewayIdentity:
        gateway_id = str(gateway_id)
        existing = self._by_gateway.get(gateway_id)
        if existing is not None:
            return existing

        # Prefer the gateway's own id when the FL protocol already accepts it.
        # Default simulator ids (``gateway-01``) therefore keep their familiar
        # worker/topic names, while arbitrary ids still get a safe mapping.
        raw = re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", gateway_id)
        if raw is not None and self._by_worker.get(gateway_id) in (None, gateway_id):
            identity = GatewayIdentity(
                gateway_id=gateway_id,
                worker_id=gateway_id,
                digest_length=0,
            )
            self._by_gateway[gateway_id] = identity
            self._by_worker[gateway_id] = gateway_id
            return identity

        # Start at 10 hex chars (40 bits).  On a real collision, extend the
        # digest rather than appending an arbitrary counter, so the mapping
        # stays a pure function of the gateway id whenever possible.
        for length in (10, 16, 24, 32, 40, 48, 56, 64):
            worker_id = candidate_worker_id(
                gateway_id, prefix=self.prefix, digest_length=length
            )
            owner = self._by_worker.get(worker_id)
            if owner is None or owner == gateway_id:
                identity = GatewayIdentity(
                    gateway_id=gateway_id,
                    worker_id=worker_id,
                    digest_length=length,
                )
                self._by_gateway[gateway_id] = identity
                self._by_worker[worker_id] = gateway_id
                return identity
        raise ValueError(
            f"could not allocate a unique worker id for gateway {gateway_id!r}"
        )

    def worker_for(self, gateway_id: str) -> str | None:
        identity = self._by_gateway.get(str(gateway_id))
        return None if identity is None else identity.worker_id

    def gateway_for_worker(self, worker_id: str) -> str | None:
        return self._by_worker.get(str(worker_id))

    def snapshot(self) -> dict[str, GatewayIdentity]:
        return dict(self._by_gateway)

    def clear(self) -> None:
        self._by_gateway.clear()
        self._by_worker.clear()


__all__ = [
    "DEFAULT_PREFIX",
    "GatewayIdentity",
    "GatewayIdentityRegistry",
    "candidate_worker_id",
    "sanitize_component",
]
