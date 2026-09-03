"""Active move engine — causal 15M / 5M / 1M state at bar i."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def _atr(arr: np.ndarray, i: int) -> float:
    v = arr[i] if i < len(arr) else np.nan
    if np.isfinite(v) and v > 0:
        return float(v)
    for k in range(max(0, i - 5), i + 1):
        if k < len(arr) and np.isfinite(arr[k]) and arr[k] > 0:
            return float(arr[k])
    return 1.0


def _progress(cl: np.ndarray, i: int, lb: int, atr: float) -> float:
    if i < lb:
        return 0.0
    return float((cl[i] - cl[i - lb]) / atr)


def _classify_progress(prog: float, cfg: dict) -> str:
    strong = cfg.get("strong_progress_atr", 1.0)
    weak = cfg.get("weak_progress_atr", 0.3)
    if prog >= strong:
        return "STRONG_UP"
    if prog >= weak:
        return "UP"
    if prog <= -strong:
        return "STRONG_DOWN"
    if prog <= -weak:
        return "DOWN"
    if abs(prog) < weak * 0.5:
        return "NEUTRAL"
    return "TRANSITION"


def active_move_at_bar(m: MTFArrays, i: int, cfg: dict) -> dict:
    """Return multi-TF active move states and normalized progress."""
    if i < 5 or i >= m.m1_n:
        return _empty()

    a1 = _atr(m.m1_atr, i)
    j = int(m.m1_to_m5[i]) if i < m.m1_n else 0
    j = min(max(j, 0), m.m5_n - 1)
    a5 = _atr(m.m5_atr, j)
    j15 = int(m.m15_idx_on_m5[j]) if j < len(m.m15_idx_on_m5) else 0
    a15 = _atr(m.m15_atr, j15) if j15 < len(m.m15_atr) else 1.0

    lb1 = cfg.get("progress_lookback_1m", 8)
    lb5 = cfg.get("progress_lookback_5m", 5)
    lb15 = cfg.get("progress_lookback_15m", 4)

    p1 = _progress(m.m1_cl, i, lb1, a1)
    p5 = _progress(m.m5_cl, j, lb5, a5) if j >= lb5 else 0.0
    p15 = _progress(m.m15_cl, j15, lb15, a15) if j15 >= lb15 else 0.0

    s1 = _classify_progress(p1, cfg)
    s5 = _classify_progress(p5, cfg)
    s15 = _classify_progress(p15, cfg)

    # Impulse magnitude (causal window)
    imp_lb = cfg.get("impulse_lookback_1m", 12)
    start = max(0, i - imp_lb)
    bull_imp = float((m.m1_hi[start : i + 1].max() - m.m1_lo[start : i + 1].min()) / a1)
    start5 = max(0, j - lb5)
    bull_imp5 = float((m.m5_hi[start5 : j + 1].max() - m.m5_lo[start5 : j + 1].min()) / a5) if j >= 1 else 0.0

    # Dominant move: 15M > 5M > 1M
    dom = _dominant(s15, s5, s1)
    dom_score = _score_state(dom)

    return {
        "active_1m": s1,
        "active_5m": s5,
        "active_15m": s15,
        "dominant_active": dom,
        "dominant_score": dom_score,
        "progress_1m_atr": p1,
        "progress_5m_atr": p5,
        "progress_15m_atr": p15,
        "impulse_1m_atr": bull_imp,
        "impulse_5m_atr": bull_imp5,
    }


def _dominant(s15: str, s5: str, s1: str) -> str:
    for s in (s15, s5, s1):
        if s in ("STRONG_UP", "STRONG_DOWN"):
            return s
    for s in (s15, s5, s1):
        if s in ("UP", "DOWN"):
            return s
    return s5 if s5 != "NEUTRAL" else s1


def _score_state(state: str) -> int:
    return {
        "STRONG_UP": 2, "UP": 1, "NEUTRAL": 0, "TRANSITION": 0,
        "DOWN": -1, "STRONG_DOWN": -2,
    }.get(state, 0)


def _empty() -> dict:
    return {
        "active_1m": "NEUTRAL", "active_5m": "NEUTRAL", "active_15m": "NEUTRAL",
        "dominant_active": "NEUTRAL", "dominant_score": 0,
        "progress_1m_atr": 0.0, "progress_5m_atr": 0.0, "progress_15m_atr": 0.0,
        "impulse_1m_atr": 0.0, "impulse_5m_atr": 0.0,
    }


def side_aligned_with_active(direction: str, active: dict) -> bool:
    dom = active["dominant_active"]
    if direction == "LONG":
        return dom in ("STRONG_UP", "UP")
    if direction == "SHORT":
        return dom in ("STRONG_DOWN", "DOWN")
    return False
