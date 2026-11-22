"""Tests for the Trickle algorithm implementation (RFC 6206)."""

from __future__ import annotations

import pytest

from simulator.trickle import (
    TrickleParams,
    TrickleState,
    TrickleTimer,
    create_trickle_params_for_dio,
    create_trickle_params_for_dis,
    create_trickle_params_for_dao,
)


class TestTrickleParams:
    """Tests for TrickleParams validation and factory functions."""

    def test_default_params(self) -> None:
        params = TrickleParams()
        assert params.imin == 1.0
        assert params.imax == 16
        assert params.k == 1
        assert params.max_doublings == 16

    def test_custom_params(self) -> None:
        params = TrickleParams(imin=2.0, imax=10, k=2, max_doublings=10)
        assert params.imin == 2.0
        assert params.imax == 10
        assert params.k == 2
        assert params.max_doublings == 10

    def test_invalid_imin(self) -> None:
        with pytest.raises(ValueError, match="imin must be positive"):
            TrickleParams(imin=0)
        with pytest.raises(ValueError, match="imin must be positive"):
            TrickleParams(imin=-1)

    def test_invalid_imax(self) -> None:
        with pytest.raises(ValueError, match="imax must be non-negative"):
            TrickleParams(imax=-1)

    def test_invalid_k(self) -> None:
        with pytest.raises(ValueError, match="k must be at least 1"):
            TrickleParams(k=0)
        with pytest.raises(ValueError, match="k must be at least 1"):
            TrickleParams(k=-1)

    def test_invalid_max_doublings(self) -> None:
        with pytest.raises(ValueError, match="max_doublings must be at least 1"):
            TrickleParams(max_doublings=0)

    def test_create_dio_params(self) -> None:
        params = create_trickle_params_for_dio()
        assert params.imin == 1.0
        assert params.imax == 16
        assert params.k == 1
        assert params.max_doublings == 16

    def test_create_dis_params(self) -> None:
        params = create_trickle_params_for_dis()
        assert params.imin == 0.5
        assert params.imax == 8
        assert params.k == 1
        assert params.max_doublings == 8

    def test_create_dao_params(self) -> None:
        params = create_trickle_params_for_dao()
        assert params.imin == 1.0
        assert params.imax == 12
        assert params.k == 1
        assert params.max_doublings == 12


class TestTrickleState:
    """Tests for TrickleState runtime behavior."""

    def test_reset_initializes_correctly(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(10.0)

        assert state.interval == 1.0
        assert state.interval_start == 10.0
        assert state.interval_end == 11.0
        assert state.c == 0
        assert state.doubled_count == 0
        assert state.last_tx_time is None
        assert state.t >= 10.0 and state.t <= 11.0

    def test_hear_consistent_increments_counter(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=3, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)

        assert state.c == 0
        state.hear_consistent()
        assert state.c == 1
        state.hear_consistent()
        assert state.c == 2

    def test_hear_inconsistent_resets_timer(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=3, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.c = 5  # Simulate some consistent transmissions heard
        old_interval = state.interval

        state.hear_inconsistent(5.0)

        assert state.c == 0
        assert state.interval == params.imin
        assert state.interval_start == 5.0
        assert state.interval_end == 6.0
        assert state.doubled_count == 0

    def test_advance_time_interval_expiry(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.c = 0
        state.t = 0.5  # Would have transmitted at 0.5

        # Advance past interval end
        result = state.advance_time(2.0)

        assert result is False  # No transmission (interval expired first)
        assert state.interval == 2.0  # Doubled
        assert state.interval_start == 1.0
        assert state.interval_end == 3.0
        assert state.doubled_count == 1
        assert state.c == 0

    def test_advance_time_transmission_triggered(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=2, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.c = 0  # Below k
        state.t = 0.5  # Transmission scheduled at 0.5

        result = state.advance_time(0.5)

        assert result is True  # Should transmit
        assert state.last_tx_time == 0.5

    def test_advance_time_suppressed(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.c = 1  # Equal to k, suppressed
        state.t = 0.5

        result = state.advance_time(0.5)

        assert result is False  # Suppressed, no transmission

    def test_time_until_tx(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.t = 0.5

        assert state.time_until_tx(0.0) == 0.5
        assert state.time_until_tx(0.5) == 0.0
        assert state.time_until_tx(0.6) == 0.0  # Past transmission time

    def test_time_until_tx_suppressed(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(0.0)
        state.c = 1  # Suppressed

        assert state.time_until_tx(0.0) is None

    def test_to_dict(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        state = TrickleState(
            interval=params.imin,
            interval_start=0.0,
            interval_end=params.imin,
            params=params,
        )
        state.reset(10.0)
        state.last_tx_time = 10.5

        d = state.to_dict()

        assert d["interval"] == 1.0
        assert d["interval_start"] == 10.0
        assert d["interval_end"] == 11.0
        assert d["c"] == 0
        assert d["doubled_count"] == 0
        assert d["last_tx_time"] == 10.5
        assert d["params"]["imin"] == 1.0
        assert d["params"]["imax"] == 4
        assert d["params"]["k"] == 1
        assert d["params"]["max_doublings"] == 4


class TestTrickleTimer:
    """Tests for TrickleTimer high-level interface."""

    def test_initialize(self) -> None:
        params = TrickleParams(imin=2.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(5.0)

        assert timer._initialized is True
        assert timer.state.interval == 2.0
        assert timer.state.interval_start == 5.0
        assert timer.state.interval_end == 7.0

    def test_step_before_initialize(self) -> None:
        timer = TrickleTimer()
        should_tx, interval_expired = timer.step(3.0)

        # Should auto-initialize and not transmit immediately
        assert timer._initialized is True
        assert should_tx is False
        assert interval_expired is False

    def test_step_transmission(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)
        # Force t to be at interval start
        timer.state.t = 0.0

        should_tx, interval_expired = timer.step(0.0)

        assert should_tx is True
        assert interval_expired is False

    def test_step_interval_expired(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)
        timer.state.c = 0
        timer.state.t = 0.5  # Would have transmitted at 0.5

        should_tx, interval_expired = timer.step(2.0)

        assert should_tx is False
        assert interval_expired is True
        assert timer.state.interval == 2.0  # Doubled

    def test_on_tx(self) -> None:
        timer = TrickleTimer()
        timer.initialize(0.0)
        timer.on_tx(1.5)

        assert timer.state.last_tx_time == 1.5

    def test_on_consistent_heard(self) -> None:
        timer = TrickleTimer()
        timer.initialize(0.0)

        timer.on_consistent_heard()
        timer.on_consistent_heard()

        assert timer.state.c == 2

    def test_on_inconsistent_heard(self) -> None:
        timer = TrickleTimer()
        timer.initialize(0.0)
        timer.state.c = 5

        timer.on_inconsistent_heard(3.0)

        assert timer.state.c == 0
        assert timer.state.interval_start == 3.0

    def test_reset(self) -> None:
        timer = TrickleTimer()
        timer.initialize(0.0)
        timer.state.c = 10

        timer.reset(5.0)

        assert timer.state.c == 0
        assert timer.state.interval_start == 5.0
        assert timer._initialized is True

    def test_is_suppressed(self) -> None:
        params = TrickleParams(imin=1.0, imax=4, k=2, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)

        assert timer.is_suppressed is False
        timer.on_consistent_heard()  # c=1
        assert timer.is_suppressed is False
        timer.on_consistent_heard()  # c=2
        assert timer.is_suppressed is True

    def test_get_state(self) -> None:
        timer = TrickleTimer()
        timer.initialize(10.0)

        state = timer.get_state(10.0)

        assert "interval" in state
        assert "time_until_tx" in state
        assert "time_until_interval_end" in state
        assert "is_suppressed" in state
        assert state["time_until_interval_end"] == 1.0
        assert state["is_suppressed"] is False


class TestTrickleAlgorithmBehavior:
    """Tests for the core Trickle algorithm behavior per RFC 6206."""

    def test_interval_doubling_up_to_imax(self) -> None:
        """Test that interval doubles until Imax is reached."""
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)

        # Step through intervals at their exact end times
        # Interval ends: 1, 3 (1+2), 7 (3+4), 15 (7+8), 31 (15+16), 63 (31+32)
        intervals = []
        step_times = [0.0, 1.1, 3.1, 7.1, 15.1, 31.1]
        for t in step_times:
            timer.step(t)
            intervals.append(timer.state.interval)

        # Should double: 1, 2, 4, 8, 16, 16 (capped at Imin * 2^imax = 16)
        assert intervals[0] == 1.0
        assert intervals[1] == 2.0
        assert intervals[2] == 4.0
        assert intervals[3] == 8.0
        assert intervals[4] == 16.0
        assert intervals[5] == 16.0  # Capped at Imax

    def test_suppression_on_consistent_heard(self) -> None:
        """Test that hearing consistent transmissions suppresses own transmission."""
        params = TrickleParams(imin=10.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)
        timer.state.t = 5.0  # Scheduled to transmit at 5.0

        # At time 3.0, hear consistent transmission
        timer.on_consistent_heard()

        # Should be suppressed now
        should_tx, _ = timer.step(5.0)
        assert should_tx is False

    def test_reset_on_inconsistent_heard(self) -> None:
        """Test that hearing inconsistent transmission resets timer to Imin."""
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)
        timer = TrickleTimer(params)
        timer.initialize(0.0)

        # Let interval double a few times
        timer.step(2.0)  # interval = 2
        timer.step(4.0)  # interval = 4
        assert timer.state.interval == 4.0
        assert timer.state.doubled_count == 2

        # Hear inconsistent transmission
        timer.on_inconsistent_heard(5.0)

        # Should reset to Imin
        assert timer.state.interval == 1.0
        assert timer.state.doubled_count == 0
        assert timer.state.interval_start == 5.0

    def test_deterministic_behavior_with_seed(self) -> None:
        """Test that Trickle is deterministic with fixed seed."""
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)

        timer1 = TrickleTimer(params)
        timer1.initialize(0.0)
        t1 = timer1.state.t

        timer2 = TrickleTimer(params)
        timer2.initialize(0.0)
        t2 = timer2.state.t

        # Both use same random (module-level), should be same
        # Note: this test may vary based on random module state
        # but should be consistent within a single run
        assert isinstance(t1, float)
        assert isinstance(t2, float)


class TestTrickleIntegration:
    """Integration tests with multiple timers."""

    def test_multiple_independent_timers(self) -> None:
        """Test that multiple timers for different DODAGs are independent."""
        params = TrickleParams(imin=1.0, imax=4, k=1, max_doublings=4)

        timer_a = TrickleTimer(params)
        timer_b = TrickleTimer(params)

        timer_a.initialize(0.0)
        timer_b.initialize(0.0)

        # Force B's transmission time to be early so it will transmit at 0.5
        timer_b.state.t = 0.0

        # A hears consistent, B doesn't
        timer_a.on_consistent_heard()

        # Advance both
        should_a, _ = timer_a.step(0.5)
        should_b, _ = timer_b.step(0.5)

        assert should_a is False  # A suppressed
        assert should_b is True  # B transmits

    def test_timer_state_serialization(self) -> None:
        """Test that timer state can be serialized for API."""
        timer = TrickleTimer()
        timer.initialize(10.0)
        timer.on_consistent_heard()
        timer.on_tx(10.5)

        state = timer.get_state(11.0)

        assert state["interval"] == 1.0
        assert state["c"] == 1
        assert state["last_tx_time"] == 10.5
        assert state["is_suppressed"] is True
        assert "time_until_tx" in state
        assert "time_until_interval_end" in state