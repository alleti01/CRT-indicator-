"""15M and 5M context evaluated at 1M bar index (completed HTF only)."""
from __future__ import annotations

import numpy as np

from phase58b.research.context_15m import compute_15m_context, score_15m_for_direction, strong_contradiction
from phase58b.research.context_5m import compute_5m_structure
from phase58b.research.location_5m import compute_5m_location
from phase58b.research.precompute import MTFArrays


def ctx15_at_1m(m: MTFArrays, i: int, cfg: dict) -> dict:
    j = int(m.m1_to_m5[i]) if i < m.m1_n else 0
    return compute_15m_context(m, j, cfg)


def ctx5_at_1m(m: MTFArrays, i: int, cfg: dict) -> dict:
    j = int(m.m1_to_m5[i]) if i < m.m1_n else 0
    return compute_5m_structure(m, j, cfg)


def loc5_at_1m(m: MTFArrays, i: int, direction: str, cfg: dict) -> dict:
    j = int(m.m1_to_m5[i]) if i < m.m1_n else 0
    return compute_5m_location(m, j, direction, cfg)


def location_score(m: MTFArrays, i: int, direction: str, cfg: dict) -> tuple[int, list[str]]:
    """Location quality — is something important likely here?"""
    from phase58.research.location import compute_location

    m1 = m1_market_view(m, cfg.get("swing_period", 5))
    loc1 = compute_location(m1, i, direction)
    loc5 = loc5_at_1m(m, i, direction, cfg)
    score = min(3, loc1["score"] + loc5["score"])
    reasons = loc1["reasons"] + loc5["reasons"]
    return score, reasons


def direction_score(ctx15: dict, ctx5: dict, direction: str) -> tuple[int, list[str]]:
    """Direction quality — which way is favored?"""
    c15, r15 = score_15m_for_direction(ctx15, direction)
    bull = ctx5.get("bull", 0)
    bear = ctx5.get("bear", 0)
    if direction == "LONG":
        s5 = min(2, bull)
    else:
        s5 = min(2, bear)
    reasons = r15 + ctx5.get("reasons", [])
    return c15 + s5, reasons


def m1_market_view(m: MTFArrays, swing: int = 5):
    """Build Phase58 MarketArrays view from MTFArrays (cached swings)."""
    from phase52.research.swings import (
        precompute_last2_swing_highs,
        precompute_last2_swing_lows,
        precompute_swing_highs,
        precompute_swing_lows,
    )
    from phase58.research.precompute import MarketArrays

    if not hasattr(m, "_p58d_m1_view"):
        body = np.abs(m.m1_cl - m.m1_op)
        _sh1, _sh2 = precompute_last2_swing_highs(m.m1_hi, swing)
        _sl1, _sl2 = precompute_last2_swing_lows(m.m1_lo, swing)
        m._p58d_m1_view = MarketArrays(
            hi=m.m1_hi, lo=m.m1_lo, cl=m.m1_cl, op=m.m1_op, atr=m.m1_atr,
            n=m.m1_n, idx=m.m1_idx,
            sh=precompute_swing_highs(m.m1_hi, swing),
            sl=precompute_swing_lows(m.m1_lo, swing),
            sh1=_sh1, sh2=_sh2, sl1=_sl1, sl2=_sl2,
            m5_cl=m.m5_cl, m5_op=m.m5_op, m5_hi=m.m5_hi, m5_lo=m.m5_lo,
            m5_atr=m.m5_atr, m5_idx=m.m1_to_m5,
            m15_cl=m.m15_cl, m15_op=m.m15_op, m15_hi=m.m15_hi, m15_lo=m.m15_lo,
            m15_atr=m.m15_atr, m15_idx=m.m1_to_m5,
            body=body, avg_body=body,
        )
    return m._p58d_m1_view
