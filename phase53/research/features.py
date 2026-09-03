"""Causal feature extraction — vectorized over event index."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase52.research.swings import precompute_swing_highs, precompute_swing_lows
from phase53.config import DEFAULT_SWING, RANGE_WINDOWS_15M, RANGE_WINDOWS_5M, RTH_SESSION
from phase53.research.data import htf_bar_index


def _range_position_arr(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, ii: np.ndarray, lb: int) -> np.ndarray:
    out = np.full(len(ii), np.nan)
    for k, i in enumerate(ii):
        if i < lb:
            continue
        rh = np.max(hi[i - lb + 1 : i + 1])
        rl = np.min(lo[i - lb + 1 : i + 1])
        rng = rh - rl
        if rng > 0:
            out[k] = np.clip((cl[i] - rl) / rng, 0, 1)
    return out


def attach_features(
    events: pd.DataFrame,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    p44_state: pd.Series,
    core_ctx: pd.DataFrame,
) -> pd.DataFrame:
    if events.empty:
        return events
    ev = events.sort_values("timestamp_ct").reset_index(drop=True)
    ii = ev["entry_i"].values.astype(int)
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr1 = m1["atr"].values.astype(float)
    body = np.abs(cl - op)
    avg_body = pd.Series(body).rolling(20, min_periods=20).mean().values
    atr_mean = pd.Series(atr1).rolling(100, min_periods=100).mean().values
    sh_arr = precompute_swing_highs(hi, DEFAULT_SWING)
    sl_arr = precompute_swing_lows(lo, DEFAULT_SWING)

    m5_i = htf_bar_index(m1.index, m5.index)
    m15_i = htf_bar_index(m1.index, m15.index)
    j5 = m5_i[ii]
    j15 = m15_i[ii]

    m5_hi = m5["high"].values.astype(float)
    m5_lo = m5["low"].values.astype(float)
    m5_cl = m5["close"].values.astype(float)
    m5_op = m5["open"].values.astype(float)
    m5_atr = m5["atr"].values.astype(float) if "atr" in m5.columns else np.full(len(m5), np.nan)
    m15_hi = m15["high"].values.astype(float)
    m15_lo = m15["low"].values.astype(float)
    m15_cl = m15["close"].values.astype(float)
    m15_op = m15["open"].values.astype(float)
    m15_atr = m15["atr"].values.astype(float) if "atr" in m15.columns else np.full(len(m15), np.nan)

    atr = atr1[ii]
    d = np.where(ev["direction"].values == "LONG", 1, -1)
    lvl = ev["structure_level"].values.astype(float)

    feat = pd.DataFrame(
        {
            "swing_high": sh_arr[ii],
            "swing_low": sl_arr[ii],
            "dist_swing_high_atr": (cl[ii] - sh_arr[ii]) / atr,
            "dist_swing_low_atr": (sl_arr[ii] - cl[ii]) / atr,
            "break_dist_atr": (cl[ii] - lvl) / atr * d,
            "body_atr": body[ii] / atr,
            "range_atr": (hi[ii] - lo[ii]) / atr,
            "body_vs_avg": body[ii] / avg_body[ii],
            "close_loc": (cl[ii] - lo[ii]) / np.maximum(hi[ii] - lo[ii], 1e-9),
            "mom_1": (cl[ii] - cl[np.maximum(ii - 1, 0)]) / atr,
            "mom_3": (cl[ii] - cl[np.maximum(ii - 3, 0)]) / atr,
            "mom_5": (cl[ii] - cl[np.maximum(ii - 5, 0)]) / atr,
            "mom_10": (cl[ii] - cl[np.maximum(ii - 10, 0)]) / atr,
            "atr": atr,
            "atr_ratio": atr / atr_mean[ii],
            "m5_mom": (m5_cl[j5] - m5_cl[np.maximum(j5 - 3, 0)]) / m5_atr[j5],
            "m15_mom_4": (m15_cl[j15] - m15_cl[np.maximum(j15 - 4, 0)]) / m15_atr[j15],
            "m15_body_atr": np.abs(m15_cl[j15] - m15_op[j15]) / m15_atr[j15],
            "ext_30min_atr": np.abs(cl[ii] - cl[np.maximum(ii - 30, 0)]) / atr,
            "ext_60min_atr": np.abs(cl[ii] - cl[np.maximum(ii - 60, 0)]) / atr,
            "phase44_active": (p44_state.values[ii] != "NONE").astype(int),
            "core_b1_active": core_ctx["b1_active"].values[ii],
            "core_authorized": core_ctx["core_authorized"].values[ii],
            "min_since_p44": core_ctx["min_since_p44"].values[ii],
            "min_since_core_entry": core_ctx["min_since_core_entry"].values[ii],
        }
    )
    for lb in RANGE_WINDOWS_15M:
        feat[f"m15_range_pos_{lb}"] = _range_position_arr(m15_hi, m15_lo, m15_cl, j15, lb)
    for lb in RANGE_WINDOWS_5M:
        feat[f"m5_range_pos_{lb}"] = _range_position_arr(m5_hi, m5_lo, m5_cl, j5, lb)

    m5_dir = np.sign(feat["m5_mom"].fillna(0)).astype(int)
    m15_dir = np.sign(feat["m15_mom_4"].fillna(0)).astype(int)
    feat["mtf_1m_5m_align"] = (m5_dir == d).astype(int)
    feat["mtf_1m_15m_align"] = (m15_dir == d).astype(int)
    feat["countertrend_15m"] = ((m15_dir != 0) & (m15_dir != d)).astype(int)

    ts = pd.to_datetime(ev["timestamp_ct"])
    mins = ts.dt.hour * 60 + ts.dt.minute
    feat["session_minute"] = mins - (9 * 60 + 30)
    feat["dow"] = ts.dt.dayofweek
    buckets = []
    for m in mins:
        if m < 9 * 60 + 30 or m >= 16 * 60:
            buckets.append("other")
        elif m < 10 * 60 + 30:
            buckets.append("open")
        elif m < 11 * 60 + 30:
            buckets.append("morning")
        elif m < 13 * 60 + 30:
            buckets.append("midday")
        elif m < 15 * 60:
            buckets.append("afternoon")
        else:
            buckets.append("close")
    feat["session_bucket"] = buckets

    # reversal sequence
    prev_dir = ev["direction"].shift(1).map({"LONG": 1, "SHORT": -1})
    feat["is_reversal"] = (prev_dir != ev["direction"].map({"LONG": 1, "SHORT": -1})).astype(int)
    feat["min_since_prev_event"] = ts.diff().dt.total_seconds() / 60.0

    return pd.concat([ev, feat], axis=1)


def feature_columns(df: pd.DataFrame) -> list[str]:
    exclude = {
        "event_id",
        "timestamp_ct",
        "direction",
        "event_type",
        "structure_level",
        "entry_i",
        "phase44_state",
        "session_bucket",
        "prev_event_type",
    }
    numeric = []
    for c in df.columns:
        if c in exclude or c.startswith("opp_") or c.startswith("mfe_") or c.startswith("mae_") or c in ("net_R", "gross_R", "MFE_R", "MAE_R", "score", "fold", "decile"):
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            numeric.append(c)
    return numeric
