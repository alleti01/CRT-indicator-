"""Phase64 — matched non-Phase58 control locations."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

SESSION_BUCKETS = [
    (0, 6, "overnight"),
    (6, 9, "pre_market"),
    (9, 11, "opening"),
    (11, 14, "midday"),
    (14, 16, "afternoon"),
    (16, 24, "late"),
]


def _session_bucket(hour: int) -> str:
    for lo, hi, name in SESSION_BUCKETS:
        if lo <= hour < hi:
            return name
    return "late"


def _atr_tertile(atr: float, q33: float, q66: float) -> str:
    if atr <= q33:
        return "LOW"
    if atr <= q66:
        return "NORMAL"
    return "HIGH"


def build_exclusion_mask(n: int, signal_is: np.ndarray, gap: int = 30) -> np.ndarray:
    """Bars within gap of any Phase58 raw signal are excluded from controls."""
    mask = np.zeros(n, dtype=bool)
    for si in signal_is:
        lo = max(0, int(si) - gap)
        hi = min(n, int(si) + gap + 1)
        mask[lo:hi] = True
    return mask


def build_match_bins(idx: pd.DatetimeIndex, atr: np.ndarray) -> pd.DataFrame:
    """Causal bin labels per bar."""
    hours = idx.hour + idx.minute / 60.0
    sessions = [_session_bucket(int(h)) for h in hours]
    valid_atr = atr[np.isfinite(atr) & (atr > 0)]
    q33, q66 = np.percentile(valid_atr, [33.33, 66.67])
    regimes = [_atr_tertile(float(a) if np.isfinite(a) and a > 0 else q33, q33, q66) for a in atr]
    return pd.DataFrame({
        "bar_i": np.arange(len(idx)),
        "year": idx.year,
        "session": sessions,
        "atr_regime": regimes,
        "atr": atr,
    })


def match_controls(
    events: pd.DataFrame,
    all_signal_is: np.ndarray,
    idx: pd.DatetimeIndex,
    atr: np.ndarray,
    n_bars: int,
    gap: int = 30,
    min_forward: int = 61,
    seed: int = 64,
) -> pd.DataFrame:
    """
    1:1 matched controls — same year, session, ATR regime.
    Deterministic selection via hash(event_i).
    """
    exclude = build_exclusion_mask(n_bars, all_signal_is, gap)
    bins = build_match_bins(idx, atr)

    eligible = bins[(~exclude[bins["bar_i"]]) & (bins["bar_i"] < n_bars - min_forward)].copy()
    eligible["bin_key"] = (
        eligible["year"].astype(str) + "_" + eligible["session"] + "_" + eligible["atr_regime"]
    )

    pools: dict[str, np.ndarray] = {}
    for key, grp in eligible.groupby("bin_key"):
        pools[key] = grp["bar_i"].values.astype(int)

    valid_atr = atr[np.isfinite(atr) & (atr > 0)]
    q33, q66 = np.percentile(valid_atr, [33.33, 66.67])

    # Pre-index fallbacks
    fb_year_session: dict[tuple, np.ndarray] = {}
    fb_year: dict[int, np.ndarray] = {}
    for (year, session), grp in eligible.groupby(["year", "session"]):
        fb_year_session[(int(year), session)] = grp["bar_i"].values.astype(int)
    for year, grp in eligible.groupby("year"):
        fb_year[int(year)] = grp["bar_i"].values.astype(int)
    global_pool = eligible["bar_i"].values.astype(int)

    rows = []
    for _, ev in events.iterrows():
        ei = int(ev["signal_i"])
        year = int(idx[ei].year)
        session = _session_bucket(idx[ei].hour)
        regime = _atr_tertile(float(ev["atr"]), q33, q66)
        key = f"{year}_{session}_{regime}"
        pool = pools.get(key, np.array([], dtype=int))
        if len(pool) == 0:
            pool = fb_year_session.get((year, session), np.array([], dtype=int))
        if len(pool) == 0:
            pool = fb_year.get(year, np.array([], dtype=int))
        if len(pool) == 0:
            pool = global_pool
        h = int(hashlib.md5(f"{seed}_{ei}".encode()).hexdigest(), 16)
        ci = int(pool[h % len(pool)])
        rows.append({
            "event_i": ci,
            "signal_i": ci,
            "matched_to": ei,
            "match_key": key,
            "atr": float(atr[ci]) if np.isfinite(atr[ci]) and atr[ci] > 0 else float(ev["atr"]),
            "direction": "CONTROL",
            "group": "CONTROL",
        })
    return pd.DataFrame(rows)


def match_quality(events: pd.DataFrame, controls: pd.DataFrame, idx: pd.DatetimeIndex, atr: np.ndarray) -> dict:
    """Pre-event match sanity check."""
    def _stats(df, label):
        is_ = df["signal_i"].values.astype(int)
        atrs = [float(atr[i]) for i in is_ if i < len(atr) and np.isfinite(atr[i]) and atr[i] > 0]
        return {
            f"{label}_median_atr": float(np.median(atrs)) if atrs else 0.0,
            f"{label}_mean_atr": float(np.mean(atrs)) if atrs else 0.0,
        }
    ev = _stats(events, "phase58")
    ct = _stats(controls, "control")
    ev_sessions = [_session_bucket(idx[int(i)].hour) for i in events["signal_i"]]
    ct_sessions = [_session_bucket(idx[int(i)].hour) for i in controls["signal_i"]]
    from collections import Counter
    ev_sess = Counter(ev_sessions)
    ct_sess = Counter(ct_sessions)
    sess_diff = sum(abs(ev_sess.get(k, 0) / len(events) - ct_sess.get(k, 0) / len(controls)) for k in set(ev_sess) | set(ct_sess))
    atr_ratio = ev["phase58_median_atr"] / ct["control_median_atr"] if ct["control_median_atr"] > 0 else 1.0
    quality = "GOOD" if sess_diff < 0.15 and 0.85 <= atr_ratio <= 1.15 else "ACCEPTABLE" if sess_diff < 0.30 else "POOR"
    return {
        **ev, **ct,
        "session_distribution_diff": float(sess_diff),
        "atr_ratio": float(atr_ratio),
        "match_quality": quality,
        "major_mismatch": quality == "POOR",
    }
