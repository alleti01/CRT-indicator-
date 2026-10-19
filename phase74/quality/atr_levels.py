"""Stop, target and size from NinjaTrader's 1-minute bars, with no chart reading.

Stop = entry -/+ stop_atr x ATR(14) of 3-minute candles built from the 1-minute
bars; target = target_r x that distance; quantity = risk_usd / (distance x point
value), capped at max_qty. Used by the live order path (levels.source = "atr")
and by the shadow profiles, so both always agree.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from phase73.market_data.bar import Bar
from phase74.quality.htf_bias import resample


@dataclass(frozen=True)
class AtrLevelConfig:
    stop_atr: float = 1.5
    target_r: float = 2.0
    risk_usd: float = 600.0
    point_value: float = 2.0  # MNQ
    min_stop_points: float = 4.0
    max_qty: int = 10  # NinjaTrader preflight allows 1-10 (MAX_QUANTITY)
    max_bar_age_minutes: int = 10
    tick_size: float = 0.25

    @classmethod
    def from_dict(cls, raw: dict) -> AtrLevelConfig:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in (raw or {}).items() if k in known})


@dataclass(frozen=True)
class AtrLevels:
    stop: float
    target: float
    qty: int
    stop_points: float
    atr3: float


def atr3(bars: Sequence[Bar], n: int = 14) -> float:
    threes = resample(bars, 3)
    if len(threes) < n + 1:
        return 0.0
    w = threes[-(n + 1):]
    return sum(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close)) for p, b in zip(w, w[1:])) / n


def _tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 2)


def compute_atr_levels(
    side: str, price: float, t: datetime, bars: Sequence[Bar], cfg: AtrLevelConfig
) -> tuple[AtrLevels | None, str]:
    """Return (levels, "") or (None, reason). Uses only bars closed by `t`."""
    if side not in ("LONG", "SHORT"):
        return None, "BAD_SIDE"
    hist = [b for b in bars if b.timestamp <= t]
    if not hist or t - hist[-1].timestamp > timedelta(minutes=cfg.max_bar_age_minutes):
        return None, "STALE_BARS"
    atr = atr3(hist)
    if atr <= 0:
        return None, "NO_ATR"
    dist = max(cfg.stop_atr * atr, cfg.min_stop_points)
    qty = max(1, min(cfg.max_qty, math.floor(cfg.risk_usd / (dist * cfg.point_value))))
    sgn = 1 if side == "LONG" else -1
    stop = _tick(price - sgn * dist, cfg.tick_size)
    target = _tick(price + sgn * dist * cfg.target_r, cfg.tick_size)
    return AtrLevels(stop=stop, target=target, qty=qty, stop_points=round(abs(price - stop), 2), atr3=round(atr, 2)), ""
