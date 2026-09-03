"""5M location — structural placement for ARMED setups."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def compute_5m_location(m: MTFArrays, j: int, direction: str, cfg: dict) -> dict:
    if j < 30:
        return dict(score=0, reasons=[], pb_depth_pct=0.0, swing_dist_atr=np.nan)

    a = _atr(m.m5_atr[j], m.m5_atr, j)
    prox = cfg.get("swing_proximity_atr", 0.5)
    pb_min = cfg.get("pullback_min_depth_pct", 0.15)
    pb_max = cfg.get("pullback_max_depth_pct", 0.6)
    reasons: list[str] = []
    score = 0

    if direction == "LONG":
        swing = m.m5_sl[j]
        if np.isfinite(swing) and abs(m.m5_cl[j] - swing) / a < prox:
            score += 1
            reasons.append("5M_NEAR_SWING_LOW")
    else:
        swing = m.m5_sh[j]
        if np.isfinite(swing) and abs(m.m5_cl[j] - swing) / a < prox:
            score += 1
            reasons.append("5M_NEAR_SWING_HIGH")

    lb = 20
    start = max(0, j - lb)
    if direction == "LONG":
        recent_high = m.m5_hi[start : j + 1].max()
        impulse = recent_high - m.m5_lo[start : j + 1].min()
        pb_depth = (recent_high - m.m5_cl[j]) / impulse if impulse > 0 else 0
    else:
        recent_low = m.m5_lo[start : j + 1].min()
        impulse = m.m5_hi[start : j + 1].max() - recent_low
        pb_depth = (m.m5_cl[j] - recent_low) / impulse if impulse > 0 else 0

    if pb_min <= pb_depth <= pb_max:
        score += 1
        reasons.append("5M_PB_DEPTH_OK")

    # 15M structural area proximity (soft location)
    if direction == "LONG":
        lvl = m.m15_lo[j]
        if np.isfinite(lvl) and abs(m.m5_cl[j] - lvl) / a < prox * 1.5:
            score += 1
            reasons.append("5M_NEAR_15M_LOW")
    else:
        lvl = m.m15_hi[j]
        if np.isfinite(lvl) and abs(m.m5_cl[j] - lvl) / a < prox * 1.5:
            score += 1
            reasons.append("5M_NEAR_15M_HIGH")

    swing_dist = abs(m.m5_cl[j] - swing) / a if np.isfinite(swing) else np.nan
    return dict(score=min(score, 2), reasons=reasons, pb_depth_pct=pb_depth, swing_dist_atr=swing_dist)


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
