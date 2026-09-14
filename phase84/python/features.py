"""Causal 1M price-action features at Phase72A signal time."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase84.python.config import EXT_ATR_BUCKETS, RANGE_WINDOWS


def _rolling_high_low(hi: np.ndarray, lo: np.ndarray, i: int, window: int) -> tuple[float, float]:
    start = max(0, i - window + 1)
    return float(np.max(hi[start:i + 1])), float(np.min(lo[start:i + 1]))


def _atr_at(atr: np.ndarray, i: int) -> float:
    v = float(atr[i])
    return v if v > 0 else 1.0


def compute_features_at_signal(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_i: int,
    direction: str,
) -> dict:
    """All features known at close of signal bar T."""
    i = signal_i
    d = 1 if direction == "LONG" else -1
    atr_t = _atr_at(atr, i)
    close_t = float(cl[i])

    out: dict = {"signal_i": i, "atr_signal": atr_t}

    # Mid-range
    for w in RANGE_WINDOWS:
        rh, rl = _rolling_high_low(hi, lo, i, w)
        span = rh - rl
        rp = (close_t - rl) / span if span > 1e-9 else 0.5
        out[f"range_position_{w}"] = float(np.clip(rp, 0, 1))
        out[f"rolling_high_{w}"] = rh
        out[f"rolling_low_{w}"] = rl

    # Extension / chase (direction normalized)
    for lb in (3, 5, 10):
        if i >= lb:
            move = (close_t - float(cl[i - lb])) * d
            out[f"move_{lb}m_ATR"] = move / atr_t
        else:
            out[f"move_{lb}m_ATR"] = np.nan

    for w in (5, 10, 20):
        rh, rl = _rolling_high_low(hi, lo, i - 1, w)  # exclude current bar for extrema ref
        if d == 1:
            out[f"dist_from_{w}m_extreme_ATR"] = (rh - close_t) / atr_t
        else:
            out[f"dist_from_{w}m_extreme_ATR"] = (close_t - rl) / atr_t

    # Signal bar geometry
    rng = float(hi[i] - lo[i])
    body = abs(float(cl[i] - op[i]))
    out["signal_bar_range_ATR"] = rng / atr_t
    out["signal_bar_body_ATR"] = body / atr_t
    out["signal_body_frac"] = body / rng if rng > 1e-9 else 0.0
    if rng > 1e-9:
        out["signal_close_loc"] = (close_t - lo[i]) / rng
    else:
        out["signal_close_loc"] = 0.5

    # Local level before signal (causal, bars [i-w, i-1])
    w = 20
    if i >= w:
        local_hi, local_lo = _rolling_high_low(hi, lo, i - 1, w)
    else:
        local_hi, local_lo = _rolling_high_low(hi, lo, max(0, i - 1), max(1, i))

    out["local_high_pre"] = local_hi
    out["local_low_pre"] = local_lo

    # Breakout acceptance at signal bar
    if d == 1:
        wick_break = float(hi[i]) > local_hi
        close_accept = float(cl[i]) > local_hi
        failed_break = wick_break and float(cl[i]) <= local_hi
        opposite_wick = (float(hi[i]) - max(float(op[i]), float(cl[i]))) / atr_t
    else:
        wick_break = float(lo[i]) < local_lo
        close_accept = float(cl[i]) < local_lo
        failed_break = wick_break and float(cl[i]) >= local_lo
        opposite_wick = (min(float(op[i]), float(cl[i])) - float(lo[i])) / atr_t

    out["break_wick"] = bool(wick_break)
    out["break_close_accept"] = bool(close_accept)
    out["failed_break"] = bool(failed_break)
    out["opposite_wick_ATR"] = float(opposite_wick)

    # Immediate commitment
    out["directional_body"] = float(cl[i] - op[i]) * d
    out["directional_body_ATR"] = out["directional_body"] / atr_t

    if i >= 1:
        if d == 1:
            out["close_beyond_prior_high"] = float(cl[i]) > float(hi[i - 1])
        else:
            out["close_beyond_prior_low"] = float(cl[i]) < float(lo[i - 1])
    else:
        out["close_beyond_prior_high"] = False
        out["close_beyond_prior_low"] = False

    return out


def enrich_signals(signals: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float) if "atr" in m1.columns else (hi - lo)

    rows = []
    for _, sig in signals.iterrows():
        si = int(sig["signal_i"])
        if si < 20 or si >= len(cl) - 65:
            continue
        feats = compute_features_at_signal(hi, lo, cl, op, atr, si, sig["phase72a_direction"])
        rows.append({**sig.to_dict(), **feats})

    return pd.DataFrame(rows)


def bucket_range_position(rp: float) -> str:
    if rp < 0.2:
        return "0.00-0.20"
    if rp < 0.4:
        return "0.20-0.40"
    if rp < 0.6:
        return "0.40-0.60"
    if rp < 0.8:
        return "0.60-0.80"
    return "0.80-1.00"


def bucket_extension(ext: float) -> str:
    for b in EXT_ATR_BUCKETS:
        if ext <= b:
            return f"<={b}"
    return f">{EXT_ATR_BUCKETS[-1]}"
