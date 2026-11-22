"""Trickle algorithm implementation (RFC 6206).

The Trickle algorithm manages the transmission interval for control messages
(DIO, DIS, DAO) in RPL. Each node maintains independent Trickle timers per
DODAG (per RPL instance) to avoid synchronized transmissions.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrickleParams:
    """Trickle algorithm parameters (RFC 6206 Section 4)."""

    imin: float = 1.0  # Imin in seconds (minimum interval)
    imax: int = 16  # Imax as power of 2 multiplier (Imax = Imin * 2^imax)
    k: int = 1  # redundancy constant (suppressions threshold)
    max_doublings: int = 16  # maximum interval doublings

    def __post_init__(self) -> None:
        if self.imin <= 0:
            raise ValueError("imin must be positive")
        if self.imax < 0:
            raise ValueError("imax must be non-negative")
        if self.k < 1:
            raise ValueError("k must be at least 1")
        if self.max_doublings < 1:
            raise ValueError("max_doublings must be at least 1")


@dataclass
class TrickleState:
    """Runtime state for a single Trickle timer."""

    interval: float  # current interval I
    interval_start: float  # simulation time when interval started
    interval_end: float  # simulation time when interval ends
    c: int = 0  # counter of consistent transmissions heard
    t: float = 0.0  # random transmission time within interval
    doubled_count: int = 0  # number of times interval has doubled
    last_tx_time: float | None = None  # last transmission time
    params: TrickleParams = field(default_factory=TrickleParams)

    def reset(self, now: float, params: TrickleParams | None = None) -> None:
        """Reset Trickle timer to Imin (RFC 6206 Section 5)."""
        if params is not None:
            self.params = params
        self.interval = self.params.imin
        self.interval_start = now
        self.interval_end = now + self.interval
        self.c = 0
        self.t = now + random.uniform(0, self.interval)
        self.doubled_count = 0
        self.last_tx_time = None

    def hear_consistent(self) -> None:
        """Called when a consistent transmission is heard (increment c)."""
        self.c += 1

    def hear_inconsistent(self, now: float) -> None:
        """Called when an inconsistent transmission is heard (reset timer)."""
        self.reset(now)

    def advance_time(self, now: float) -> bool:
        """Advance time, return True if transmission should occur now."""
        if now >= self.interval_end:
            # Interval expired - double interval up to Imax
            self.interval_start = self.interval_end
            if self.doubled_count < self.params.max_doublings:
                self.interval = min(self.interval * 2, self.params.imin * (2 ** self.params.imax))
                self.doubled_count += 1
            else:
                self.interval = self.params.imin * (2 ** self.params.imax)
            self.interval_end = self.interval_start + self.interval
            self.c = 0
            self.t = self.interval_start + random.uniform(0, self.interval)
            return False

        if now >= self.t and self.c < self.params.k:
            # Transmission time reached and not suppressed
            self.last_tx_time = now
            return True

        return False

    def time_until_tx(self, now: float) -> float | None:
        """Return time until next scheduled transmission, or None if suppressed."""
        if self.c >= self.params.k:
            return None
        if now < self.t:
            return self.t - now
        return 0.0

    def time_until_interval_end(self, now: float) -> float:
        """Return time until current interval ends."""
        return max(0.0, self.interval_end - now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize state for API/debugging."""
        return {
            "interval": self.interval,
            "interval_start": self.interval_start,
            "interval_end": self.interval_end,
            "c": self.c,
            "t": self.t,
            "doubled_count": self.doubled_count,
            "last_tx_time": self.last_tx_time,
            "params": {
                "imin": self.params.imin,
                "imax": self.params.imax,
                "k": self.params.k,
                "max_doublings": self.params.max_doublings,
            },
        }


class TrickleTimer:
    """Trickle timer for a specific DODAG (per RFC 6206)."""

    def __init__(self, params: TrickleParams | None = None) -> None:
        self.params = params or TrickleParams()
        self.state = TrickleState(
            interval=self.params.imin,
            interval_start=0.0,
            interval_end=self.params.imin,
            params=self.params,
        )
        self._initialized = False

    def initialize(self, now: float, params: TrickleParams | None = None) -> None:
        """Initialize or re-initialize the timer."""
        if params is not None:
            self.params = params
            self.state.params = params
        self.state.reset(now, self.params)
        self._initialized = True

    def step(self, now: float) -> tuple[bool, bool]:
        """Advance time by one step.

        Returns:
            (should_transmit, interval_expired)
        """
        if not self._initialized:
            self.initialize(now)

        interval_expired = now >= self.state.interval_end
        should_transmit = self.state.advance_time(now)
        return should_transmit, interval_expired

    def on_tx(self, now: float) -> None:
        """Record a transmission at current time."""
        self.state.last_tx_time = now

    def on_consistent_heard(self) -> None:
        """Record a consistent transmission heard from another node."""
        self.state.hear_consistent()

    def on_inconsistent_heard(self, now: float) -> None:
        """Record an inconsistent transmission heard - reset timer."""
        self.state.hear_inconsistent(now)

    def reset(self, now: float, params: TrickleParams | None = None) -> None:
        """Explicit reset of the timer."""
        self.state.reset(now, params)
        self._initialized = True

    @property
    def is_suppressed(self) -> bool:
        """Check if timer is currently suppressed (c >= k)."""
        return self.state.c >= self.state.params.k

    @property
    def current_interval(self) -> float:
        return self.state.interval

    @property
    def time_until_tx(self) -> float | None:
        """Time until next transmission (requires current time)."""
        # This needs to be called with current time from engine
        return None

    def get_state(self, now: float) -> dict[str, Any]:
        """Get current state with computed time-until values."""
        state_dict = self.state.to_dict()
        state_dict["time_until_tx"] = self.state.time_until_tx(now)
        state_dict["time_until_interval_end"] = self.state.time_until_interval_end(now)
        state_dict["is_suppressed"] = self.is_suppressed
        return state_dict


def create_trickle_params_for_dio() -> TrickleParams:
    """Create default Trickle parameters for DIO messages."""
    return TrickleParams(
        imin=1.0,  # 1 second minimum interval
        imax=16,  # 2^16 = 65536 seconds max interval (~18 hours)
        k=1,  # suppress after 1 consistent transmission
        max_doublings=16,
    )


def create_trickle_params_for_dis() -> TrickleParams:
    """Create default Trickle parameters for DIS messages."""
    return TrickleParams(
        imin=0.5,  # faster DIS
        imax=8,  # shorter max interval
        k=1,
        max_doublings=8,
    )


def create_trickle_params_for_dao() -> TrickleParams:
    """Create default Trickle parameters for DAO messages."""
    return TrickleParams(
        imin=1.0,
        imax=12,
        k=1,
        max_doublings=12,
    )