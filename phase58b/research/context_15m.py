"""15M market map — soft context evidence at each 5M decision bar."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def compute_15m_context(m: MTFArrays, j: int, cfg: dict) -> dict:
    """Causal 15M context using last completed 15M bar only."""
    if j < 20:
        return _neutral("WARMUP")

    a5 = _atr(m.m5_atr[j], m.m5_atr, j)
    j15 = int(m.m15_idx_on_m5[j])
    if j15 < 2:
        return _neutral("NO_15M")

    a15 = _atr(m.m15_atr[j], m.m15_atr, j)
    reasons: list[str] = []
    bull = 0.0
    bear = 0.0

    # Structural swing progression on 15M (via aligned series)
    sh1 = m.m15_hi[j]
    sh2 = m.m15_hi[max(0, j - 4)]
    sl1 = m.m15_lo[j]
    sl2 = m.m15_lo[max(0, j - 4)]
    if np.isfinite(sh1) and np.isfinite(sh2):
        if sh1 > sh2:
            bull += 0.5
            reasons.append("15M_HH")
        elif sh1 < sh2:
            bear += 0.5
            reasons.append("15M_LH")
    if np.isfinite(sl1) and np.isfinite(sl2):
        if sl1 > sl2:
            bull += 0.5
            reasons.append("15M_HL")
        elif sl1 < sl2:
            bear += 0.5
            reasons.append("15M_LL")

    # Directional progress (15M momentum over ~3 bars = 45min)
    lb = min(j, 12)
    if lb >= 3:
        prog = (m.m15_cl[j] - m.m15_cl[j - lb]) / a15
        if prog > 0.5:
            bull += 1.0
            reasons.append("15M_PROG_UP")
        elif prog < -0.5:
            bear += 1.0
            reasons.append("15M_PROG_DN")

    # Impulse magnitude vs ATR
    start = max(0, j - 8)
    impulse = m.m15_hi[start : j + 1].max() - m.m15_lo[start : j + 1].min()
    if impulse / a15 > 2.0:
        if m.m15_cl[j] > m.m15_cl[start]:
            bull += 0.5
            reasons.append("15M_IMP_BULL")
        else:
            bear += 0.5
            reasons.append("15M_IMP_BEAR")

    # Range position on 15M
    rng_hi = m.m15_hi[start : j + 1].max()
    rng_lo = m.m15_lo[start : j + 1].min()
    rng = rng_hi - rng_lo
    pos = (m.m15_cl[j] - rng_lo) / rng if rng > 0 else 0.5
    if pos > 0.7:
        bull += 0.5
        reasons.append("15M_RANGE_HIGH")
    elif pos < 0.3:
        bear += 0.5
        reasons.append("15M_RANGE_LOW")

    # Momentum persistence (consecutive 15M-aligned closes)
    ups = downs = 0
    for k in range(1, min(4, j)):
        d = m.m15_cl[j - k + 1] - m.m15_cl[j - k] if j - k >= 0 else 0
        if d > 0:
            ups += 1
        elif d < 0:
            downs += 1
    if ups >= 2:
        bull += 0.5
        reasons.append("15M_PERSIST_UP")
    if downs >= 2:
        bear += 0.5
        reasons.append("15M_PERSIST_DN")

    # Expansion vs contraction
    recent_range = m.m5_hi[j] - m.m5_lo[j]
    prior_range = np.mean([m.m5_hi[j - k] - m.m5_lo[j - k] for k in range(1, 5) if j - k >= 0])
    if prior_range > 0 and recent_range / prior_range > 1.3:
        if m.m5_cl[j] > m.m5_op[j]:
            bull += 0.5
            reasons.append("15M_EXP_BULL")
        else:
            bear += 0.5
            reasons.append("15M_EXP_BEAR")

    net = bull - bear
    strength = float(np.clip(net, -2, 2))

    if strength >= 1.0:
        state = "BULLISH"
    elif strength <= -1.0:
        state = "BEARISH"
    elif abs(strength) < 0.5 and (bull + bear) > 0:
        state = "TRANSITION"
    else:
        state = "NEUTRAL"

    return {
        "state": state,
        "strength": strength,
        "bull": bull,
        "bear": bear,
        "score": int(np.clip(round(strength), -2, 2)),
        "reasons": reasons,
        "range_pos": pos if rng > 0 else 0.5,
        "impulse_atr": impulse / a15 if a15 > 0 else 0,
    }


def score_15m_for_direction(ctx15: dict, direction: str) -> tuple[int, list[str]]:
    """Soft 15M score for trade direction (-2 to +2)."""
    s = ctx15.get("score", int(np.clip(round(ctx15.get("strength", 0)), -2, 2)))
    reasons = []
    if direction == "LONG":
        if s > 0:
            reasons.append(f"15M_SUPPORT_{s}")
            return min(2, s), reasons
        if s < -1:
            reasons.append(f"15M_CONTRA_{s}")
            return max(-2, s), reasons
        reasons.append("15M_NEUTRAL")
        return 0, reasons
    else:
        if s < 0:
            reasons.append(f"15M_SUPPORT_{abs(s)}")
            return min(2, abs(s)), reasons
        if s > 1:
            reasons.append(f"15M_CONTRA_{s}")
            return max(-2, -s), reasons
        reasons.append("15M_NEUTRAL")
        return 0, reasons


def strong_contradiction(ctx15: dict, direction: str, m: MTFArrays, j: int) -> tuple[bool, list[str]]:
    """Strong HTF contradiction — 15M against + progress + 5M expansion."""
    reasons = []
    if direction == "LONG":
        if ctx15["state"] != "BEARISH" or ctx15["strength"] > -1.5:
            return False, reasons
        lb = min(j, 6)
        prog = (m.m5_cl[j] - m.m5_cl[j - lb]) / _atr(m.m5_atr[j], m.m5_atr, j)
        if prog >= -0.3:
            return False, reasons
        body = m.m5_cl[j] - m.m5_op[j]
        if body >= 0:
            return False, reasons
        reasons.extend(["STRONG_CONTRA_LONG", "15M_BEAR_ACCEL", "5M_SELL_EXPAND"])
        return True, reasons
    else:
        if ctx15["state"] != "BULLISH" or ctx15["strength"] < 1.5:
            return False, reasons
        lb = min(j, 6)
        prog = (m.m5_cl[j] - m.m5_cl[j - lb]) / _atr(m.m5_atr[j], m.m5_atr, j)
        if prog <= 0.3:
            return False, reasons
        body = m.m5_cl[j] - m.m5_op[j]
        if body <= 0:
            return False, reasons
        reasons.extend(["STRONG_CONTRA_SHORT", "15M_BULL_ACCEL", "5M_BUY_EXPAND"])
        return True, reasons


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0


def _neutral(tag: str) -> dict:
    return {
        "state": "NEUTRAL",
        "strength": 0.0,
        "bull": 0.0,
        "bear": 0.0,
        "score": 0,
        "reasons": [tag],
        "range_pos": 0.5,
        "impulse_atr": 0.0,
    }
