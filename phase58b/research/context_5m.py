"""5M structure context — primary decision-layer bias."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def compute_5m_structure(m: MTFArrays, j: int, cfg: dict) -> dict:
    if j < 20:
        return dict(direction="NEUTRAL", score=0, reasons=[], bull=0, bear=0)

    a = _atr(m.m5_atr[j], m.m5_atr, j)
    reasons: list[str] = []
    bull = 0
    bear = 0

    sh1, sh2 = m.m5_sh1[j], m.m5_sh2[j]
    sl1, sl2 = m.m5_sl1[j], m.m5_sl2[j]
    if np.isfinite(sh1) and np.isfinite(sh2):
        if sh1 > sh2:
            bull += 1
            reasons.append("5M_HH")
        elif sh1 < sh2:
            bear += 1
            reasons.append("5M_LH")
    if np.isfinite(sl1) and np.isfinite(sl2):
        if sl1 > sl2:
            bull += 1
            reasons.append("5M_HL")
        elif sl1 < sl2:
            bear += 1
            reasons.append("5M_LL")

    lb = cfg.get("momentum_lookback_5m", 5)
    if j >= lb:
        mom = (m.m5_cl[j] - m.m5_cl[j - lb]) / a
        if mom > 0.3:
            bull += 1
            reasons.append("5M_MOM_UP")
        elif mom < -0.3:
            bear += 1
            reasons.append("5M_MOM_DN")

    net = bull - bear
    if net >= 2:
        direction = "BULLISH"
    elif net <= -2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    score = min(2, bull if direction == "BULLISH" else bear if direction == "BEARISH" else max(bull, bear))
    return dict(direction=direction, score=score, reasons=reasons, bull=bull, bear=bear)


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
