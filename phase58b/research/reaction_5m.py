"""5M reaction evidence — causal micro-sequence at decision layer."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def compute_5m_reactions(m: MTFArrays, j: int, direction: str, cfg: dict) -> dict:
    reasons: list[str] = []
    score = 0
    a = _atr(m.m5_atr[j], m.m5_atr, j)

    if j >= 2:
        if direction == "LONG":
            fe = m.m5_lo[j] < m.m5_lo[j - 1] and (m.m5_lo[j - 1] - m.m5_lo[j]) / a < 0.15 and m.m5_cl[j] > m.m5_cl[j - 1]
        else:
            fe = m.m5_hi[j] > m.m5_hi[j - 1] and (m.m5_hi[j] - m.m5_hi[j - 1]) / a < 0.15 and m.m5_cl[j] < m.m5_cl[j - 1]
        if fe:
            score += 1
            reasons.append("5M_FAILED_EXT")

    body = m.m5_cl[j] - m.m5_op[j]
    thresh = cfg.get("body_threshold_atr", 0.3)
    if direction == "LONG" and body > 0 and abs(body) / a >= thresh:
        score += 1
        reasons.append("5M_DIR_RESPONSE")
    elif direction == "SHORT" and body < 0 and abs(body) / a >= thresh:
        score += 1
        reasons.append("5M_DIR_RESPONSE")

    bar_range = m.m5_hi[j] - m.m5_lo[j]
    wick_pct = cfg.get("wick_rejection_pct", 0.5)
    if bar_range > 0:
        if direction == "LONG" and m.m5_cl[j] > m.m5_op[j]:
            lw = min(m.m5_cl[j], m.m5_op[j]) - m.m5_lo[j]
            if lw / bar_range >= wick_pct:
                score += 1
                reasons.append("5M_REJECTION")
        elif direction == "SHORT" and m.m5_cl[j] < m.m5_op[j]:
            uw = m.m5_hi[j] - max(m.m5_cl[j], m.m5_op[j])
            if uw / bar_range >= wick_pct:
                score += 1
                reasons.append("5M_REJECTION")

    lb = cfg.get("deceleration_lookback", 3)
    if j >= lb + 1:
        if direction == "LONG":
            counter = [abs(m.m5_cl[j - k] - m.m5_cl[j - k - 1]) for k in range(1, lb + 1) if m.m5_cl[j - k] < m.m5_cl[j - k - 1]]
        else:
            counter = [abs(m.m5_cl[j - k] - m.m5_cl[j - k - 1]) for k in range(1, lb + 1) if m.m5_cl[j - k] > m.m5_cl[j - k - 1]]
        if len(counter) >= 2 and counter[0] < counter[-1] * 0.7:
            score += 1
            reasons.append("5M_MOM_LOSS")

    if j >= 3:
        if direction == "LONG":
            reclaim = m.m5_cl[j] > m.m5_cl[j - 2] and m.m5_cl[j - 1] < m.m5_cl[j - 2]
        else:
            reclaim = m.m5_cl[j] < m.m5_cl[j - 2] and m.m5_cl[j - 1] > m.m5_cl[j - 2]
        if reclaim:
            score += 1
            reasons.append("5M_RECLAIM")

    mb = cfg.get("micro_shift_bars", 2)
    if j >= mb:
        if direction == "LONG":
            shifted = all(m.m5_cl[j - k] > m.m5_cl[j - k - 1] for k in range(mb))
        else:
            shifted = all(m.m5_cl[j - k] < m.m5_cl[j - k - 1] for k in range(mb))
        if shifted:
            score += 1
            reasons.append("5M_MICRO_SHIFT")

    return dict(score=min(score, 3), reasons=reasons)


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
