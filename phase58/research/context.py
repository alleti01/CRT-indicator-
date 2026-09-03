"""Market context — directional bias from structure and HTF alignment.

All inputs are precomputed array lookups at bar index i. No future data.
"""
from __future__ import annotations

import numpy as np

from phase58.research.precompute import MarketArrays


def compute_context(m: MarketArrays, i: int) -> dict:
    """Compute directional context at bar i. Returns direction, confidence, reason codes."""
    if i < 20:
        return dict(direction="NEUTRAL", confidence=0, reasons=[])

    a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
    reasons = []
    bull_score = 0
    bear_score = 0

    # 1M swing progression
    cur_sh = m.sh[i]; prev_sh = m.sh[max(0, i - 10)]
    cur_sl = m.sl[i]; prev_sl = m.sl[max(0, i - 10)]
    if np.isfinite(cur_sh) and np.isfinite(prev_sh):
        if cur_sh > prev_sh:
            bull_score += 1; reasons.append("SWING_HH")
        elif cur_sh < prev_sh:
            bear_score += 1; reasons.append("SWING_LH")
    if np.isfinite(cur_sl) and np.isfinite(prev_sl):
        if cur_sl > prev_sl:
            bull_score += 1; reasons.append("SWING_HL")
        elif cur_sl < prev_sl:
            bear_score += 1; reasons.append("SWING_LL")

    # 1M momentum (5-bar net close change / ATR)
    if i >= 5:
        mom = (m.cl[i] - m.cl[i - 5]) / a
        if mom > 0.3:
            bull_score += 1; reasons.append("MOM_BULL")
        elif mom < -0.3:
            bear_score += 1; reasons.append("MOM_BEAR")

    # 5M direction (last completed 5M bar)
    j5 = int(m.m5_idx[i])
    if j5 > 0:
        m5_body = m.m5_cl[i] - m.m5_op[i]
        m5a = m.m5_atr[i] if np.isfinite(m.m5_atr[i]) and m.m5_atr[i] > 0 else a
        if m5_body / m5a > 0.2:
            bull_score += 1; reasons.append("M5_BULL")
        elif m5_body / m5a < -0.2:
            bear_score += 1; reasons.append("M5_BEAR")

    # 15M direction (last completed 15M close vs prior)
    j15 = int(m.m15_idx[i])
    if j15 > 0 and i > 15:
        m15_mom = m.m15_cl[i] - m.m15_cl[max(0, i - 15)]
        m15a = m.m15_atr[i] if np.isfinite(m.m15_atr[i]) and m.m15_atr[i] > 0 else a
        if m15_mom / m15a > 0.3:
            bull_score += 1; reasons.append("M15_BULL")
        elif m15_mom / m15a < -0.3:
            bear_score += 1; reasons.append("M15_BEAR")

    net = bull_score - bear_score
    total = bull_score + bear_score
    if net >= 2:
        direction = "BULLISH"
    elif net <= -2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    confidence = min(100, abs(net) * 25)
    return dict(direction=direction, confidence=confidence, reasons=reasons,
                bull_score=bull_score, bear_score=bear_score)
