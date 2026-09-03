"""Causal price leg detection using Phase52 swing progression.

A leg is a directional price move detectable sequentially without future pivots.
Uses confirmed swing highs/lows with DEFAULT_SWING-bar lag.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase57.config import DEFAULT_SWING


@dataclass
class PriceLeg:
    direction: str           # "BULL" or "BEAR"
    start_i: int
    end_i: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    start_price: float
    end_price: float
    distance: float          # absolute
    distance_atr: float
    duration: int            # bars
    efficiency: float        # |net move| / total path traveled
    displacement: float      # max single-bar body / ATR during leg
    structure_broken: bool   # did a causal swing get broken
    leg_id: str = ""


def _path_traveled(hi: np.ndarray, lo: np.ndarray, start: int, end: int) -> float:
    total = 0.0
    for j in range(start, end + 1):
        total += hi[j] - lo[j]
    return total


def detect_legs(
    m1: pd.DataFrame,
    *,
    swing: int = DEFAULT_SWING,
    min_distance_atr: float = 1.0,
    start_i: int = 100,
) -> list[PriceLeg]:
    """Detect causal price legs from 1M data using swing progression.

    A bullish leg starts when a new higher swing-high is confirmed and price
    has moved >= min_distance_atr from the most recent swing-low.
    Detection is sequential: no future pivot information used.
    """
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)

    sh = precompute_swing_highs(hi, swing)
    sl = precompute_swing_lows(lo, swing)
    sh1, sh2 = precompute_last2_swing_highs(hi, swing)
    sl1, sl2 = precompute_last2_swing_lows(lo, swing)

    legs: list[PriceLeg] = []
    leg_counter = 0

    # Track active leg state
    bull_start_i = None
    bull_start_price = None
    bear_start_i = None
    bear_start_price = None
    prev_sh = np.nan
    prev_sl = np.nan

    for i in range(max(start_i, swing * 2 + 1), n):
        a = atr[i] if np.isfinite(atr[i]) else 1.0
        cur_sh = sh[i]
        cur_sl = sl[i]

        # Bullish leg: new higher swing-high confirmed
        if np.isfinite(cur_sh) and np.isfinite(prev_sh) and cur_sh > prev_sh:
            if np.isfinite(cur_sl):
                dist = cur_sh - cur_sl
                if dist / a >= min_distance_atr:
                    # Find approximate start (last swing low)
                    s_i = max(start_i, i - 200)
                    for k in range(i, s_i, -1):
                        if np.isfinite(sl[k]) and lo[k] <= cur_sl + a * 0.1:
                            s_i = k
                            break
                    path = _path_traveled(hi, lo, s_i, i)
                    eff = dist / path if path > 0 else 0.0
                    max_disp = 0.0
                    for k in range(s_i, i + 1):
                        body = abs(cl[k] - op[k])
                        max_disp = max(max_disp, body / a)
                    broken = bool(np.isfinite(sh2[i]) and cur_sh > sh2[i])
                    leg_counter += 1
                    legs.append(PriceLeg(
                        direction="BULL",
                        start_i=s_i,
                        end_i=i,
                        start_ts=idx[s_i],
                        end_ts=idx[i],
                        start_price=float(lo[s_i]),
                        end_price=float(cur_sh),
                        distance=dist,
                        distance_atr=dist / a,
                        duration=i - s_i,
                        efficiency=eff,
                        displacement=max_disp,
                        structure_broken=broken,
                        leg_id=f"LEG-{leg_counter:07d}",
                    ))

        # Bearish leg: new lower swing-low confirmed
        if np.isfinite(cur_sl) and np.isfinite(prev_sl) and cur_sl < prev_sl:
            if np.isfinite(cur_sh):
                dist = cur_sh - cur_sl
                if dist / a >= min_distance_atr:
                    s_i = max(start_i, i - 200)
                    for k in range(i, s_i, -1):
                        if np.isfinite(sh[k]) and hi[k] >= cur_sh - a * 0.1:
                            s_i = k
                            break
                    path = _path_traveled(hi, lo, s_i, i)
                    eff = dist / path if path > 0 else 0.0
                    max_disp = 0.0
                    for k in range(s_i, i + 1):
                        body = abs(cl[k] - op[k])
                        max_disp = max(max_disp, body / a)
                    broken = bool(np.isfinite(sl2[i]) and cur_sl < sl2[i])
                    leg_counter += 1
                    legs.append(PriceLeg(
                        direction="BEAR",
                        start_i=s_i,
                        end_i=i,
                        start_ts=idx[s_i],
                        end_ts=idx[i],
                        start_price=float(hi[s_i]),
                        end_price=float(cur_sl),
                        distance=dist,
                        distance_atr=dist / a,
                        duration=i - s_i,
                        efficiency=eff,
                        displacement=max_disp,
                        structure_broken=broken,
                        leg_id=f"LEG-{leg_counter:07d}",
                    ))

        if np.isfinite(cur_sh):
            prev_sh = cur_sh
        if np.isfinite(cur_sl):
            prev_sl = cur_sl

    return legs


def legs_to_df(legs: list[PriceLeg]) -> pd.DataFrame:
    return pd.DataFrame([{
        "leg_id": l.leg_id,
        "direction": l.direction,
        "start_i": l.start_i,
        "end_i": l.end_i,
        "start_ts": l.start_ts,
        "end_ts": l.end_ts,
        "start_price": l.start_price,
        "end_price": l.end_price,
        "distance": l.distance,
        "distance_atr": l.distance_atr,
        "duration": l.duration,
        "efficiency": l.efficiency,
        "displacement": l.displacement,
        "structure_broken": l.structure_broken,
    } for l in legs])
