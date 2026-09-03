"""Instrument adapter — normalized market-agnostic interface."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    symbol: str
    tick_size: float
    point_value: float
    session: str
    timezone: str
    cost_per_rt_usd: float

    def cost_r(self, entry: float, stop: float, mult: float = 1.0) -> float:
        risk = abs(entry - stop)
        if risk <= 0:
            return 0.0
        return (self.cost_per_rt_usd * mult) / (risk * self.point_value)


NQ = InstrumentSpec(
    symbol="NQ",
    tick_size=0.25,
    point_value=20.0,
    session="0830-1500",
    timezone="America/Chicago",
    cost_per_rt_usd=14.50,
)
