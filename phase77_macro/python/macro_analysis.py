"""Path, random-direction, matched controls, volatility vs information."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase77.python.gates import aggregate_paths, path_metrics, random_direction_eval

from .config import MAX_SMD_ACCEPT, MIN_EFFECT_FP11, N_TOO_SMALL, RANDOM_SEED_COUNT, RANDOM_SEED_START


MATCH_COV = ("atr", "range_5m", "range_15m", "range_30m", "session_range_pct")


def add_range_covariates(feat: pd.DataFrame) -> pd.DataFrame:
    out = feat.copy()
    out["range_5m"] = out["high"].rolling(5, min_periods=1).max() - out["low"].rolling(5, min_periods=1).min()
    out["range_15m"] = out["high"].rolling(15, min_periods=1).max() - out["low"].rolling(15, min_periods=1).min()
    out["range_30m"] = out["high"].rolling(30, min_periods=1).max() - out["low"].rolling(30, min_periods=1).min()
    dev_h, dev_l = out.get("dev_high", out["high"]), out.get("dev_low", out["low"])
    width = dev_h - dev_l
    out["session_range_pct"] = np.where(width > 0, (out["close"] - dev_l) / width, np.nan)
    return out


def standardized_mean_diff(a: pd.Series, b: pd.Series) -> float:
    a, b = a.dropna().astype(float), b.dropna().astype(float)
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2)
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else 0.0


def two_sided_path_metrics(signals: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    """Non-directional excursion for volatility-vs-information check."""
    pathed = path_metrics(signals, m1)
    if pathed.empty:
        return pathed
    idx = m1.index
    pos = {ts: i for i, ts in enumerate(idx)}
    highs, lows = m1["high"].values, m1["low"].values
    ts_list = []
    for _, row in pathed.iterrows():
        start = pos.get(row["entry_ts"])
        if start is None:
            ts_list.append(np.nan)
            continue
        end = min(start + 15, len(m1) - 1)
        h, l = highs[start : end + 1], lows[start : end + 1]
        ep = row["entry_price"]
        atr = row["atr"]
        up = (h.max() - ep) / atr if atr > 0 else 0
        dn = (ep - l.min()) / atr if atr > 0 else 0
        ts_list.append(up + dn)
    pathed["two_sided_15m"] = ts_list
    pathed["sweep_both_1"] = ((pathed.get("mfe_15m", 0) >= 1) & (pathed.get("mae_15m", 0) >= 1)).astype(float)
    return pathed


def sample_size_class(n: int) -> str:
    if n < N_TOO_SMALL:
        return "N_TOO_SMALL_FOR_INFERENCE"
    if n < 100:
        return "EXPLORATORY_ONLY"
    return "INFERENCE_ELIGIBLE"


def macro_random_gate(signals: pd.DataFrame, m1: pd.DataFrame) -> dict:
    if len(signals) < N_TOO_SMALL:
        return {"status": "NOT_ELIGIBLE", "n": len(signals), "reason": "N_TOO_SMALL"}
    return random_direction_eval(signals, m1)


def lateness_vs_event(signals: pd.DataFrame, calendar: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    out = signals.copy()
    event_ts = {}
    for _, ev in calendar.iterrows():
        event_ts[ev["event_name"]] = ev["release_ts_utc"]
    move_pre = []
    for _, row in out.iterrows():
        ev_name = row.get("macro_event", "")
        t0 = event_ts.get(ev_name)
        if t0 is None:
            move_pre.append(np.nan)
            continue
        sig = row["signal_ts"]
        try:
            i0 = int(m1.index.searchsorted(t0))
            i1 = int(m1.index.searchsorted(sig))
            i0 = min(i0, len(m1) - 1)
            i1 = min(i1, len(m1) - 1)
            atr = row["atr"]
            move_pre.append(abs(m1.iloc[i1]["close"] - m1.iloc[i0]["close"]) / atr if atr > 0 else np.nan)
        except KeyError:
            move_pre.append(np.nan)
    out["move_from_event_to_signal_atr"] = move_pre
    return out
