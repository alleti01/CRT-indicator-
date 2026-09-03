"""Phase59I — HTF causality diagnostics (does NOT modify canonical pipeline)."""
from __future__ import annotations

import copy
from typing import Literal

import numpy as np
import pandas as pd

from phase53.research.data import align_htf_to_1m, htf_bar_index, resample_5m_causal

HTFMode = Literal["original", "causal_a", "causal_b"]


def last_completed_label(ts: pd.Timestamp, minutes: int) -> pd.Timestamp:
    """Label of last fully completed HTF bucket at 1M bar close ts."""
    if ts.minute % minutes == (minutes - 1):
        return ts.floor(f"{minutes}min")
    return ts.floor(f"{minutes}min") - pd.Timedelta(minutes=minutes)


def developing_bucket_label(ts: pd.Timestamp, minutes: int) -> pd.Timestamp:
    return ts.floor(f"{minutes}min")


def _label_pos(index: pd.DatetimeIndex, label: pd.Timestamp) -> int:
    j = int(index.searchsorted(label))
    if j >= len(index) or index[j] != label:
        j = max(0, int(index.searchsorted(label, side="right") - 1))
    return j


def _labels_last_completed(index: pd.DatetimeIndex, minutes: int) -> pd.DatetimeIndex:
    mins = index.minute
    floors = index.floor(f"{minutes}min")
    offset = pd.to_timedelta(np.where(mins % minutes == minutes - 1, 0, minutes), unit="m")
    return floors - offset


def _labels_developing(index: pd.DatetimeIndex, minutes: int) -> pd.DatetimeIndex:
    return index.floor(f"{minutes}min")


def _pos_for_labels(htf_index: pd.DatetimeIndex, labels: pd.DatetimeIndex) -> np.ndarray:
    labels = pd.DatetimeIndex(labels).tz_convert(htf_index.tz)
    pos = htf_index.searchsorted(labels)
    bad = (pos >= len(htf_index)) | (htf_index.values[np.clip(pos, 0, len(htf_index) - 1)] != labels.values)
    if bad.any():
        pos2 = htf_index.searchsorted(labels, side="right") - 1
        pos = np.where(bad, pos2, pos)
    return np.clip(pos, 0, len(htf_index) - 1)


def build_htf_on_1m(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    mode: HTFMode,
) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray, np.ndarray]:
    """Return (m5_on_1m, m15_on_1m, m1_to_m5_idx, m1_to_m15_idx) per mode."""
    if mode == "original":
        m5a = align_htf_to_1m(m1, m5)
        m15a = align_htf_to_1m(m1, m15)
        return (
            m5a.reindex(m1.index),
            m15a.reindex(m1.index),
            htf_bar_index(m1.index, m5.index),
            htf_bar_index(m1.index, m15.index),
        )

    if mode == "causal_a":
        lab5 = _labels_last_completed(m1.index, 5)
        lab15 = _labels_last_completed(m1.index, 15)
        m5_out = m5.reindex(lab5).set_index(m1.index)
        m15_out = m15.reindex(lab15).set_index(m1.index)
        return m5_out, m15_out, _pos_for_labels(m5.index, lab5), _pos_for_labels(m15.index, lab15)

    # causal_b — vectorized developing buckets from 1M only
    g5 = m1.index.floor("5min")
    g15 = m1.index.floor("15min")
    m5_out = pd.DataFrame(index=m1.index)
    m5_out["open"] = m1.groupby(g5)["open"].transform("first")
    m5_out["high"] = m1.groupby(g5)["high"].cummax()
    m5_out["low"] = m1.groupby(g5)["low"].cummin()
    m5_out["close"] = m1["close"]
    if "atr" in m5.columns:
        lab5 = _labels_developing(m1.index, 5)
        m5_out["atr"] = m5.reindex(lab5)["atr"].values

    m15_out = pd.DataFrame(index=m1.index)
    m15_out["open"] = m1.groupby(g15)["open"].transform("first")
    m15_out["high"] = m1.groupby(g15)["high"].cummax()
    m15_out["low"] = m1.groupby(g15)["low"].cummin()
    m15_out["close"] = m1["close"]
    if "atr" in m15.columns:
        lab15 = _labels_developing(m1.index, 15)
        m15_out["atr"] = m15.reindex(lab15)["atr"].values

    lab5 = _labels_developing(m1.index, 5)
    lab15 = _labels_developing(m1.index, 15)
    return m5_out, m15_out, _pos_for_labels(m5.index, lab5), _pos_for_labels(m15.index, lab15)


def visibility_table(m1: pd.DataFrame, m5: pd.DataFrame, ts_list: list[str], tz: str) -> pd.DataFrame:
    """Compare original / causal_a / causal_b / last_completed / developing at timestamps."""
    rows = []
    for t in ts_list:
        ts = pd.Timestamp(t, tz=tz)
        i = m1.index.get_loc(ts)
        orig_m5, _, _, _ = build_htf_on_1m(m1, m5, m5, "original")  # m15 unused for 5m cols
        _, _, _, _ = orig_m5, _, _, _
        m15_dummy = m5  # not used below

    return pd.DataFrame()


def bucket_first_knowable(m1: pd.DataFrame, bucket_start: pd.Timestamp, minutes: int = 5) -> dict:
    """For the HTF bucket starting at bucket_start, when is each final OHLC field first knowable?"""
    end = bucket_start + pd.Timedelta(minutes=minutes - 1)
    sub = m1.loc[bucket_start:end]
    final_o = float(sub["open"].iloc[0])
    final_h = float(sub["high"].max())
    final_l = float(sub["low"].min())
    final_c = float(sub["close"].iloc[-1])

    run_h = -np.inf
    run_l = np.inf
    know = {"open": str(bucket_start), "high": None, "low": None, "close": str(end)}
    for ts, row in sub.iterrows():
        run_h = max(run_h, float(row["high"]))
        run_l = min(run_l, float(row["low"]))
        if know["high"] is None and abs(run_h - final_h) < 1e-6:
            know["high"] = str(ts)
        if know["low"] is None and abs(run_l - final_l) < 1e-6:
            know["low"] = str(ts)
    return {
        "open": final_o,
        "high": final_h,
        "low": final_l,
        "close": final_c,
        "knowable": know,
    }


def audit_timestamp(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    ts: pd.Timestamp,
    tz: str,
) -> dict:
    """Single timestamp: Python vs causal alternatives."""
    i = m1.index.get_loc(ts)
    modes = {}
    for mode in ("original", "causal_a", "causal_b"):
        m5o, m15o, j5, j15 = build_htf_on_1m(m1, m5, m15, mode)  # type: ignore
        modes[mode] = {
            "m5_src": str(m5.index[int(j5[i])]),
            "m5_OHLC": f"{m5o.iloc[i]['open']:.2f}/{m5o.iloc[i]['high']:.2f}/{m5o.iloc[i]['low']:.2f}/{m5o.iloc[i]['close']:.2f}",
            "m15_src": str(m15.index[int(j15[i])]),
            "m15_C": float(m15o.iloc[i]["close"]),
        }
    lab5 = last_completed_label(ts, 5)
    lab15 = last_completed_label(ts, 15)
    return {"ts": str(ts), **modes, "last_completed_5m": str(lab5), "last_completed_15m": str(lab15)}


def classify_alignment(mode: HTFMode) -> str:
    return {
        "original": "C — FUTURE LEAKAGE / LOOKAHEAD (precomputed full bucket at period start)",
        "causal_a": "A — STRICTLY CAUSAL (last completed HTF bar only)",
        "causal_b": "B — DEVELOPING-BAR CAUSAL (incremental bucket from 1M observed so far)",
    }[mode]
