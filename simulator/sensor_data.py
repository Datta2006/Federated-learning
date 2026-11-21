"""Deterministic simulated sensor readings.

Each sensor has its own smooth random walk.  Values move gradually rather than
being re-drawn independently, and every reading is marked ``simulated``.  These
readings are intentionally not fed into the trained PM2.5 model.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulator.entities import (
    HUMIDITY_RANGE,
    PM10_RANGE,
    PM25_RANGE,
    TEMPERATURE_RANGE,
    SensorReading,
)


@dataclass(frozen=True)
class SensorDataConfig:
    """Tuning knobs for the simulated air-quality time series."""

    pm25_volatility: float = 2.0
    pm10_volatility: float = 3.0
    temperature_volatility: float = 0.15
    humidity_volatility: float = 0.8
    mean_reversion: float = 0.02

    def __post_init__(self) -> None:
        values = (
            self.pm25_volatility,
            self.pm10_volatility,
            self.temperature_volatility,
            self.humidity_volatility,
            self.mean_reversion,
        )
        if any(value < 0 for value in values):
            raise ValueError("sensor volatility and mean_reversion must be >= 0")
        if not 0.0 <= self.mean_reversion <= 1.0:
            raise ValueError("mean_reversion must be between 0 and 1")

    def to_dict(self) -> dict[str, float]:
        return {
            "pm25_volatility": self.pm25_volatility,
            "pm10_volatility": self.pm10_volatility,
            "temperature_volatility": self.temperature_volatility,
            "humidity_volatility": self.humidity_volatility,
            "mean_reversion": self.mean_reversion,
        }


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    return max(bounds[0], min(bounds[1], value))


class SensorDataGenerator:
    """Smooth, seeded generator for one sensor node."""

    def __init__(
        self,
        node_id: str,
        *,
        seed: int = 42,
        config: SensorDataConfig | None = None,
    ) -> None:
        self.node_id = node_id
        self.config = config or SensorDataConfig()
        self._rng = random.Random(f"{seed}:{node_id}")

        self._baseline_pm25 = self._rng.uniform(14.0, 90.0)
        self._baseline_pm10 = self._baseline_pm25 * self._rng.uniform(1.3, 1.9)
        self._baseline_temperature = self._rng.uniform(7.0, 31.0)
        self._baseline_humidity = self._rng.uniform(35.0, 78.0)

        self._pm25 = _clamp(
            self._baseline_pm25 + self._rng.gauss(0.0, 4.0), PM25_RANGE
        )
        self._pm10 = _clamp(
            max(self._pm25 * 1.45, self._baseline_pm10), PM10_RANGE
        )
        self._temperature = _clamp(
            self._baseline_temperature + self._rng.gauss(0.0, 1.0),
            TEMPERATURE_RANGE,
        )
        self._humidity = _clamp(
            self._baseline_humidity + self._rng.gauss(0.0, 3.0),
            HUMIDITY_RANGE,
        )

    def _walk(
        self,
        current: float,
        baseline: float,
        volatility: float,
        bounds: tuple[float, float],
    ) -> float:
        drift = self._rng.gauss(0.0, volatility)
        correction = (baseline - current) * self.config.mean_reversion
        return _clamp(current + drift + correction, bounds)

    def generate(self, timestamp: str) -> SensorReading:
        """Advance the series by one step and return a validated reading."""
        self._pm25 = self._walk(
            self._pm25,
            self._baseline_pm25,
            self.config.pm25_volatility,
            PM25_RANGE,
        )
        self._pm10 = self._walk(
            self._pm10,
            self._baseline_pm10,
            self.config.pm10_volatility,
            PM10_RANGE,
        )
        # PM10 includes PM2.5, so keep the coarse fraction at least as large.
        self._pm10 = _clamp(max(self._pm10, self._pm25), PM10_RANGE)
        self._temperature = self._walk(
            self._temperature,
            self._baseline_temperature,
            self.config.temperature_volatility,
            TEMPERATURE_RANGE,
        )
        self._humidity = self._walk(
            self._humidity,
            self._baseline_humidity,
            self.config.humidity_volatility,
            HUMIDITY_RANGE,
        )

        reading = SensorReading(
            timestamp=timestamp,
            pm25=self._pm25,
            pm10=self._pm10,
            temperature_c=self._temperature,
            humidity_pct=self._humidity,
            simulated=True,
            source="simulated_sensor",
        )
        reading.validate()
        return reading


__all__ = ["SensorDataConfig", "SensorDataGenerator"]
