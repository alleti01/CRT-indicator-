"""Structural location — where is price relative to meaningful levels?

All normalized (ATR-relative). No future data.
"""
from __future__ import annotations

import numpy as np

from phase58.research.precompute import MarketArrays


def compute_location(m: MarketArrays, i: int, direction: str) -> dict:
    """Compute location quality at bar i for given trade direction."""
    if i < 30:
        return dict(score=0, reasons=[], swing_dist_atr=np.nan, pb_depth_pct=0, range_pos=0.5)

    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    reasons = []
    score = 0

    # Distance from nearest relevant swing
    if direction == "LONG":
        swing_level = m.sl[i]  # nearest confirmed swing low
        if np.isfinite(swing_level):
            dist = abs(m.cl[i] - swing_level) / a
            if dist < 0.5:
                score += 1; reasons.append("NEAR_SWING_LOW")
    else:
        swing_level = m.sh[i]
        if np.isfinite(swing_level):
            dist = abs(m.cl[i] - swing_level) / a
            if dist < 0.5:
                score += 1; reasons.append("NEAR_SWING_HIGH")
    swing_dist = dist if np.isfinite(swing_level) else np.nan

    # Pullback depth vs recent impulse (running, no future)
    lb = 20
    start = max(0, i - lb)
    if direction == "LONG":
        recent_high = np.max(m.hi[start:i + 1])
        impulse = recent_high - np.min(m.lo[start:i + 1])
        current_depth = recent_high - m.cl[i]
    else:
        recent_low = np.min(m.lo[start:i + 1])
        impulse = np.max(m.hi[start:i + 1]) - recent_low
        current_depth = m.cl[i] - recent_low
    pb_depth_pct = current_depth / impulse if impulse > 0 else 0
    if 0.15 <= pb_depth_pct <= 0.6:
        score += 1; reasons.append("PB_HEALTHY_DEPTH")

    # Range position
    rng_hi = np.max(m.hi[start:i + 1])
    rng_lo = np.min(m.lo[start:i + 1])
    rng = rng_hi - rng_lo
    range_pos = (m.cl[i] - rng_lo) / rng if rng > 0 else 0.5
    if direction == "LONG" and range_pos < 0.35:
        score += 1; reasons.append("LOW_IN_RANGE")
    elif direction == "SHORT" and range_pos > 0.65:
        score += 1; reasons.append("HIGH_IN_RANGE")

    return dict(score=score, reasons=reasons, swing_dist_atr=swing_dist,
                pb_depth_pct=pb_depth_pct, range_pos=range_pos)
