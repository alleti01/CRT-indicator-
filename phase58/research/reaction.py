"""Early reaction evidence — 6 causal components.

Each returns (active: bool, magnitude: float). All use only bar i and past bars.
"""
from __future__ import annotations

import numpy as np

from phase58.research.precompute import MarketArrays


def failed_extension(m: MarketArrays, i: int, direction: str) -> tuple[bool, float]:
    """A: Pullback attempts new extreme but gains little progress."""
    if i < 2:
        return False, 0.0
    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    if direction == "LONG":
        prev_lo = m.lo[i - 1]
        cur_lo = m.lo[i]
        new_extreme = cur_lo < prev_lo
        progress = (prev_lo - cur_lo) / a if new_extreme else 0
        failed = new_extreme and progress < 0.15 and m.cl[i] > m.cl[i - 1]
    else:
        prev_hi = m.hi[i - 1]
        cur_hi = m.hi[i]
        new_extreme = cur_hi > prev_hi
        progress = (cur_hi - prev_hi) / a if new_extreme else 0
        failed = new_extreme and progress < 0.15 and m.cl[i] < m.cl[i - 1]
    return failed, progress


def momentum_loss(m: MarketArrays, i: int, direction: str, lookback: int = 3) -> tuple[bool, float]:
    """B: Countertrend momentum decelerating."""
    if i < lookback + 1:
        return False, 0.0
    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    if direction == "LONG":
        recent_moves = [m.cl[i - k] - m.cl[i - k - 1] for k in range(lookback)]
        selling = [abs(mv) for mv in recent_moves if mv < 0]
    else:
        recent_moves = [m.cl[i - k] - m.cl[i - k - 1] for k in range(lookback)]
        selling = [abs(mv) for mv in recent_moves if mv > 0]
    if len(selling) < 2:
        return False, 0.0
    decel = selling[0] < selling[-1] * 0.7
    mag = (selling[-1] - selling[0]) / a if selling[-1] > 0 else 0
    return decel, mag


def reclaim(m: MarketArrays, i: int, direction: str) -> tuple[bool, float]:
    """C: Close back through a known micro level."""
    if i < 3:
        return False, 0.0
    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    if direction == "LONG":
        prior_close = m.cl[i - 2]
        reclaimed = m.cl[i] > prior_close and m.cl[i - 1] < prior_close
        mag = (m.cl[i] - prior_close) / a
    else:
        prior_close = m.cl[i - 2]
        reclaimed = m.cl[i] < prior_close and m.cl[i - 1] > prior_close
        mag = (prior_close - m.cl[i]) / a
    return reclaimed, max(0, mag)


def directional_response(m: MarketArrays, i: int, direction: str, threshold_atr: float = 0.3) -> tuple[bool, float]:
    """D: Bar body > threshold ATR in trade direction."""
    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    body = m.cl[i] - m.op[i]
    if direction == "LONG":
        active = body > 0 and abs(body) / a >= threshold_atr
    else:
        active = body < 0 and abs(body) / a >= threshold_atr
    return active, abs(body) / a


def micro_shift(m: MarketArrays, i: int, direction: str, bars: int = 2) -> tuple[bool, float]:
    """E: Consecutive closes in trade direction."""
    if i < bars:
        return False, 0.0
    if direction == "LONG":
        shifted = all(m.cl[i - k] > m.cl[i - k - 1] for k in range(bars))
    else:
        shifted = all(m.cl[i - k] < m.cl[i - k - 1] for k in range(bars))
    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    mag = abs(m.cl[i] - m.cl[i - bars]) / a
    return shifted, mag


def rejection(m: MarketArrays, i: int, direction: str, wick_pct: float = 0.5) -> tuple[bool, float]:
    """F: Wick > threshold of range against pullback direction."""
    bar_range = m.hi[i] - m.lo[i]
    if bar_range <= 0:
        return False, 0.0
    if direction == "LONG":
        lower_wick = min(m.cl[i], m.op[i]) - m.lo[i]
        active = lower_wick / bar_range >= wick_pct and m.cl[i] > m.op[i]
        mag = lower_wick / bar_range
    else:
        upper_wick = m.hi[i] - max(m.cl[i], m.op[i])
        active = upper_wick / bar_range >= wick_pct and m.cl[i] < m.op[i]
        mag = upper_wick / bar_range
    return active, mag


def compute_all_reactions(m: MarketArrays, i: int, direction: str, cfg: dict) -> dict:
    """Compute all 6 reaction components. Returns dict with flags and total score."""
    results = {}
    score = 0
    reasons = []

    a, mag_a = failed_extension(m, i, direction)
    results["failed_ext"] = a
    if a: score += 1; reasons.append("FAILED_EXT")

    b, mag_b = momentum_loss(m, i, direction, cfg.get("deceleration_lookback", 3))
    results["mom_loss"] = b
    if b: score += 1; reasons.append("MOM_LOSS")

    c, mag_c = reclaim(m, i, direction)
    results["reclaim"] = c
    if c: score += 1; reasons.append("RECLAIM")

    d, mag_d = directional_response(m, i, direction, cfg.get("body_threshold_atr", 0.3))
    results["dir_response"] = d
    if d: score += 1; reasons.append("DIR_RESPONSE")

    e, mag_e = micro_shift(m, i, direction, cfg.get("micro_shift_bars", 2))
    results["micro_shift"] = e
    if e: score += 1; reasons.append("MICRO_SHIFT")

    f, mag_f = rejection(m, i, direction, cfg.get("wick_rejection_pct", 0.5))
    results["rejection"] = f
    if f: score += 1; reasons.append("REJECTION")

    results["score"] = min(score, 3)
    results["reasons"] = reasons
    return results
