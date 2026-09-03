"""Pullback detection and characterization after a price leg.

Continuous variables first — no preset Fibonacci levels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase57.research.legs import PriceLeg


@dataclass
class Pullback:
    leg: PriceLeg
    start_i: int            # first bar after leg ends where retracement begins
    deepest_i: int          # bar of maximum retracement
    depth_pts: float        # absolute depth
    depth_atr: float
    depth_pct_of_leg: float # depth / leg distance
    duration: int           # bars
    speed: float            # depth_pts / duration
    efficiency: float       # |net retrace| / total path
    overlapping_candles: int
    prior_swing_holds: bool # did the prior swing level hold?
    pullback_id: str = ""


def detect_pullbacks(
    m1: pd.DataFrame,
    legs: list[PriceLeg],
    *,
    min_depth_pct: float = 0.15,
    max_depth_pct: float = 1.0,
    max_bars: int = 60,
) -> list[Pullback]:
    """Detect pullbacks following completed legs.

    A pullback is a retracement against the leg direction that reaches at
    least min_depth_pct of the leg before price resumes or reverses.
    """
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    n = len(m1)
    pullbacks: list[Pullback] = []
    pb_counter = 0

    for leg in legs:
        if leg.end_i + 1 >= n:
            continue
        a = atr[leg.end_i] if np.isfinite(atr[leg.end_i]) else 1.0
        end = min(n, leg.end_i + 1 + max_bars)
        max_retrace = 0.0
        deepest_i = leg.end_i + 1
        start_i = leg.end_i + 1
        overlapping = 0
        path = 0.0

        for j in range(leg.end_i + 1, end):
            bar_range = hi[j] - lo[j]
            path += bar_range
            if j > leg.end_i + 1:
                prev_range = (hi[j - 1] - lo[j - 1])
                overlap = min(hi[j], hi[j - 1]) - max(lo[j], lo[j - 1])
                if overlap > 0:
                    overlapping += 1

            if leg.direction == "BULL":
                retrace = leg.end_price - lo[j]
            else:
                retrace = hi[j] - leg.end_price

            if retrace > max_retrace:
                max_retrace = retrace
                deepest_i = j

        if leg.distance <= 0:
            continue
        depth_pct = max_retrace / leg.distance
        if depth_pct < min_depth_pct or depth_pct > max_depth_pct:
            continue

        duration = deepest_i - start_i + 1
        speed = max_retrace / max(duration, 1)
        eff = max_retrace / path if path > 0 else 0.0

        # Check if prior swing holds
        if leg.direction == "BULL":
            prior_swing = leg.start_price
            holds = lo[start_i:deepest_i + 1].min() >= prior_swing
        else:
            prior_swing = leg.start_price
            holds = hi[start_i:deepest_i + 1].max() <= prior_swing

        pb_counter += 1
        pullbacks.append(Pullback(
            leg=leg,
            start_i=start_i,
            deepest_i=deepest_i,
            depth_pts=max_retrace,
            depth_atr=max_retrace / a,
            depth_pct_of_leg=depth_pct,
            duration=duration,
            speed=speed,
            efficiency=eff,
            overlapping_candles=overlapping,
            prior_swing_holds=bool(holds),
            pullback_id=f"PB-{pb_counter:07d}",
        ))
    return pullbacks


def pullbacks_to_df(pullbacks: list[Pullback]) -> pd.DataFrame:
    return pd.DataFrame([{
        "pullback_id": pb.pullback_id,
        "leg_id": pb.leg.leg_id,
        "leg_direction": pb.leg.direction,
        "start_i": pb.start_i,
        "deepest_i": pb.deepest_i,
        "depth_pts": pb.depth_pts,
        "depth_atr": pb.depth_atr,
        "depth_pct_of_leg": pb.depth_pct_of_leg,
        "duration": pb.duration,
        "speed": pb.speed,
        "efficiency": pb.efficiency,
        "overlapping_candles": pb.overlapping_candles,
        "prior_swing_holds": pb.prior_swing_holds,
    } for pb in pullbacks])
