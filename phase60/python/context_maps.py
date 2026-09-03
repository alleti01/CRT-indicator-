"""Phase60 causal HTF context — completed history + developing current bar."""
from __future__ import annotations

import numpy as np

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase58.research.location import compute_location
from phase58.research.precompute import MarketArrays
from phase58b.research.context_15m import score_15m_for_direction
from phase58b.research.precompute import MTFArrays
from phase60.python.developing_htf import DevelopingHTFArrays


def _dev(m: MTFArrays) -> DevelopingHTFArrays:
    return m.phase60  # type: ignore[attr-defined]


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0


def _j_comp(m: MTFArrays, i: int) -> int:
    return int(_dev(m).m5_completed_j[i])


def ctx5_at_1m(m: MTFArrays, i: int, cfg: dict) -> dict:
    """5M structure: swings on completed bars; momentum uses developing close."""
    j = _j_comp(m, i)
    if j < 20:
        return dict(direction="NEUTRAL", score=0, reasons=[], bull=0, bear=0)

    dev = _dev(m)
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
        mom = (dev.m5_dev_cl[i] - m.m5_cl[j - lb]) / a
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


def ctx15_at_1m(m: MTFArrays, i: int, cfg: dict) -> dict:
    """15M context: completed history + developing current OHLC at 1M i."""
    j = _j_comp(m, i)
    if j < 20:
        return _neutral("WARMUP")

    dev = _dev(m)
    j15 = int(dev.m15_completed_j[i])
    if j15 < 2:
        return _neutral("NO_15M")

    a5 = _atr(m.m5_atr[j], m.m5_atr, j)
    a15 = _atr(m15_atr_at(m, j15), m.m15_atr, j)
    reasons: list[str] = []
    bull = 0.0
    bear = 0.0

    # Swings on completed 15M only
    m15_hi_c = m15_df_hi(m, j15)
    m15_lo_c = m15_df_lo(m, j15)
    sh1 = m15_hi_c
    sh2 = m15_hi_at(m, j15 - 4) if j15 >= 4 else np.nan
    sl1 = m15_lo_c
    sl2 = m15_lo_at(m, j15 - 4) if j15 >= 4 else np.nan
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

    # Momentum: developing close vs completed history
    lb = min(j15, 12)
    if lb >= 3:
        cl_hist = m15_cl_at(m, j15 - lb)
        prog = (dev.m15_dev_cl[i] - cl_hist) / a15
        if prog > 0.5:
            bull += 1.0
            reasons.append("15M_PROG_UP")
        elif prog < -0.5:
            bear += 1.0
            reasons.append("15M_PROG_DN")

    # Impulse over completed 15M window ending at j15 + developing hi/lo for current
    start = max(0, j15 - 8)
    hist_hi = max(m15_hi_at(m, k) for k in range(start, j15 + 1))
    hist_lo = min(m15_lo_at(m, k) for k in range(start, j15 + 1))
    impulse_hi = max(hist_hi, dev.m15_dev_hi[i])
    impulse_lo = min(hist_lo, dev.m15_dev_lo[i])
    impulse = impulse_hi - impulse_lo
    if impulse / a15 > 2.0:
        if dev.m15_dev_cl[i] > m15_cl_at(m, start):
            bull += 0.5
            reasons.append("15M_IMP_BULL")
        else:
            bear += 0.5
            reasons.append("15M_IMP_BEAR")

    rng_hi = impulse_hi
    rng_lo = impulse_lo
    rng = rng_hi - rng_lo
    pos = (dev.m15_dev_cl[i] - rng_lo) / rng if rng > 0 else 0.5
    if pos > 0.7:
        bull += 0.5
        reasons.append("15M_RANGE_HIGH")
    elif pos < 0.3:
        bear += 0.5
        reasons.append("15M_RANGE_LOW")

    ups = downs = 0
    for k in range(1, min(4, j15)):
        d = m15_cl_at(m, j15 - k + 1) - m15_cl_at(m, j15 - k)
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

    recent_range = dev.m5_dev_hi[i] - dev.m5_dev_lo[i]
    prior_range = np.mean([m.m5_hi[j - k] - m.m5_lo[j - k] for k in range(1, 5) if j - k >= 0])
    if prior_range > 0 and recent_range / prior_range > 1.3:
        if dev.m5_dev_cl[i] > dev.m5_dev_op[i]:
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


def m15_atr_at(m: MTFArrays, j15: int) -> float:
    if not hasattr(m, "_m15_native"):
        m15_hi_at(m, 0)
    m15 = m._m15_native  # type: ignore[attr-defined]
    j15 = int(np.clip(j15, 0, len(m15) - 1))
    if "atr" in m15.columns:
        v = float(m15["atr"].iloc[j15])
        return v if np.isfinite(v) and v > 0 else 1.0
    return 1.0


def m15_hi_at(m: MTFArrays, j15: int) -> float:
    from phase58j.research.lw_data import load_markets_lw

    if not hasattr(m, "_m15_native"):
        _, _, m15 = load_markets_lw()
        m._m15_native = m15  # type: ignore[attr-defined]
    m15 = m._m15_native  # type: ignore[attr-defined]
    j15 = int(np.clip(j15, 0, len(m15) - 1))
    return float(m15["high"].iloc[j15])


def m15_lo_at(m: MTFArrays, j15: int) -> float:
    if not hasattr(m, "_m15_native"):
        m15_hi_at(m, 0)
    m15 = m._m15_native  # type: ignore[attr-defined]
    j15 = int(np.clip(j15, 0, len(m15) - 1))
    return float(m15["low"].iloc[j15])


def m15_cl_at(m: MTFArrays, j15: int) -> float:
    if not hasattr(m, "_m15_native"):
        m15_hi_at(m, 0)
    m15 = m._m15_native  # type: ignore[attr-defined]
    j15 = int(np.clip(j15, 0, len(m15) - 1))
    return float(m15["close"].iloc[j15])


def m15_df_hi(m: MTFArrays, j15: int) -> float:
    return m15_hi_at(m, j15)


def m15_df_lo(m: MTFArrays, j15: int) -> float:
    return m15_lo_at(m, j15)


def loc5_at_1m(m: MTFArrays, i: int, direction: str, cfg: dict) -> dict:
    j = _j_comp(m, i)
    if j < 30:
        return dict(score=0, reasons=[], pb_depth_pct=0.0, swing_dist_atr=np.nan)

    dev = _dev(m)
    a = _atr(m.m5_atr[j], m.m5_atr, j)
    prox = cfg.get("swing_proximity_atr", 0.5)
    pb_min = cfg.get("pullback_min_depth_pct", 0.15)
    pb_max = cfg.get("pullback_max_depth_pct", 0.6)
    reasons: list[str] = []
    score = 0
    cl = dev.m5_dev_cl[i]

    if direction == "LONG":
        swing = m.m5_sl[j]
        if np.isfinite(swing) and abs(cl - swing) / a < prox:
            score += 1
            reasons.append("5M_NEAR_SWING_LOW")
    else:
        swing = m.m5_sh[j]
        if np.isfinite(swing) and abs(cl - swing) / a < prox:
            score += 1
            reasons.append("5M_NEAR_SWING_HIGH")

    lb = 20
    start = max(0, j - lb)
    if direction == "LONG":
        recent_high = max(float(m.m5_hi[start:j].max()) if j > start else -np.inf, dev.m5_dev_hi[i])
        recent_low = min(float(m.m5_lo[start:j].min()) if j > start else np.inf, dev.m5_dev_lo[i])
        impulse = recent_high - recent_low
        pb_depth = (recent_high - cl) / impulse if impulse > 0 else 0
    else:
        recent_low = min(float(m.m5_lo[start:j].min()) if j > start else np.inf, dev.m5_dev_lo[i])
        recent_high = max(float(m.m5_hi[start:j].max()) if j > start else -np.inf, dev.m5_dev_hi[i])
        impulse = recent_high - recent_low
        pb_depth = (cl - recent_low) / impulse if impulse > 0 else 0

    if pb_min <= pb_depth <= pb_max:
        score += 1
        reasons.append("5M_PB_DEPTH_OK")

    j15 = int(dev.m15_completed_j[i])
    if direction == "LONG":
        lvl = m15_lo_at(m, j15) if j15 >= 0 else np.nan
        if np.isfinite(lvl) and abs(cl - lvl) / a < prox * 1.5:
            score += 1
            reasons.append("5M_NEAR_15M_LOW")
    else:
        lvl = m15_hi_at(m, j15) if j15 >= 0 else np.nan
        if np.isfinite(lvl) and abs(cl - lvl) / a < prox * 1.5:
            score += 1
            reasons.append("5M_NEAR_15M_HIGH")

    swing_dist = abs(cl - swing) / a if np.isfinite(swing) else np.nan
    return dict(score=min(score, 2), reasons=reasons, pb_depth_pct=pb_depth, swing_dist_atr=swing_dist)


def location_score(m: MTFArrays, i: int, direction: str, cfg: dict) -> tuple[int, list[str]]:
    m1 = m1_market_view(m, cfg.get("swing_period", 5))
    loc1 = compute_location(m1, i, direction)
    loc5 = loc5_at_1m(m, i, direction, cfg)
    score = min(3, loc1["score"] + loc5["score"])
    reasons = loc1["reasons"] + loc5["reasons"]
    return score, reasons


def m1_market_view(m: MTFArrays, swing: int = 5) -> MarketArrays:
    """1M MarketArrays view with developing HTF aligned per 1M."""
    if hasattr(m, "_p60_m1_view"):
        return m._p60_m1_view  # type: ignore[attr-defined]

    dev = _dev(m)
    body = np.abs(m.m1_cl - m.m1_op)
    _sh1, _sh2 = precompute_last2_swing_highs(m.m1_hi, swing)
    _sl1, _sl2 = precompute_last2_swing_lows(m.m1_lo, swing)
    m5_atr_1m = np.where(
        dev.m5_completed_j >= 0,
        m.m5_atr[np.clip(dev.m5_completed_j, 0, m.m5_n - 1)],
        np.nan,
    )
    m15_atr_1m = np.where(
        dev.m15_completed_j >= 0,
        m.m15_atr[np.clip(dev.m15_completed_j, 0, len(m.m15_cl) - 1)],
        np.nan,
    )
    m._p60_m1_view = MarketArrays(
        hi=m.m1_hi,
        lo=m.m1_lo,
        cl=m.m1_cl,
        op=m.m1_op,
        atr=m.m1_atr,
        n=m.m1_n,
        idx=m.m1_idx,
        sh=precompute_swing_highs(m.m1_hi, swing),
        sl=precompute_swing_lows(m.m1_lo, swing),
        sh1=_sh1,
        sh2=_sh2,
        sl1=_sl1,
        sl2=_sl2,
        m5_cl=dev.m5_dev_cl,
        m5_op=dev.m5_dev_op,
        m5_hi=dev.m5_dev_hi,
        m5_lo=dev.m5_dev_lo,
        m5_atr=m5_atr_1m,
        m5_idx=dev.m5_bucket_j,
        m15_cl=dev.m15_dev_cl,
        m15_op=dev.m15_dev_op,
        m15_hi=dev.m15_dev_hi,
        m15_lo=dev.m15_dev_lo,
        m15_atr=m15_atr_1m,
        m15_idx=dev.m15_bucket_j,
        body=body,
        avg_body=body,
    )
    return m._p60_m1_view  # type: ignore[attr-defined]


def strong_contradiction(ctx15: dict, direction: str, m: MTFArrays, i: int) -> tuple[bool, list[str]]:
    """Strong HTF contradiction using developing 5M at 1M index i."""
    dev = _dev(m)
    j = _j_comp(m, i)
    reasons: list[str] = []
    if direction == "LONG":
        if ctx15["state"] != "BEARISH" or ctx15["strength"] > -1.5:
            return False, reasons
        lb = min(j, 6)
        prog = (dev.m5_dev_cl[i] - m.m5_cl[j - lb]) / _atr(m.m5_atr[j], m.m5_atr, j)
        if prog >= -0.3:
            return False, reasons
        body = dev.m5_dev_cl[i] - dev.m5_dev_op[i]
        if body >= 0:
            return False, reasons
        reasons.extend(["STRONG_CONTRA_LONG", "15M_BEAR_ACCEL", "5M_SELL_EXPAND"])
        return True, reasons
    else:
        if ctx15["state"] != "BULLISH" or ctx15["strength"] < 1.5:
            return False, reasons
        lb = min(j, 6)
        prog = (dev.m5_dev_cl[i] - m.m5_cl[j - lb]) / _atr(m.m5_atr[j], m.m5_atr, j)
        if prog <= 0.3:
            return False, reasons
        body = dev.m5_dev_cl[i] - dev.m5_dev_op[i]
        if body <= 0:
            return False, reasons
        reasons.extend(["STRONG_CONTRA_SHORT", "15M_BULL_ACCEL", "5M_BUY_EXPAND"])
        return True, reasons


def direction_score(ctx15: dict, ctx5: dict, direction: str) -> tuple[int, list[str]]:
    c15, r15 = score_15m_for_direction(ctx15, direction)
    bull = ctx5.get("bull", 0)
    bear = ctx5.get("bear", 0)
    if direction == "LONG":
        s5 = min(2, bull)
    else:
        s5 = min(2, bear)
    reasons = r15 + ctx5.get("reasons", [])
    return c15 + s5, reasons


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
