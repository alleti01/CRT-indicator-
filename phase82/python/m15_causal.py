"""Causal 15M-only HTF from 1M bars — NO 5M in architecture."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase58j.research.lw_data import load_market_1m_lw


def resample_15m_causal(m1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1M → completed 15M bars (causal closed bars only)."""
    o = m1["open"].resample("15min").first()
    h = m1["high"].resample("15min").max()
    lo = m1["low"].resample("15min").min()
    c = m1["close"].resample("15min").last()
    m15 = pd.DataFrame({"open": o, "high": h, "low": lo, "close": c}).dropna(how="any")
    if "atr" in m1.columns:
        m15["atr"] = m1["atr"].resample("15min").last()
    else:
        tr = pd.concat(
            [m15["high"] - m15["low"], (m15["high"] - m15["close"].shift(1)).abs(), (m15["low"] - m15["close"].shift(1)).abs()],
            axis=1,
        ).max(axis=1)
        m15["atr"] = tr.rolling(14, min_periods=14).mean()
    return m15


def _bucket_start(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.floor("15min")


def _is_bucket_close(ts: pd.Timestamp) -> bool:
    return ts.minute % 15 == 14


@dataclass
class M15CausalArrays:
    """Per-1M causal 15M context (15M only — USES_5M = NO)."""

    n: int
    idx: pd.DatetimeIndex
    hi: np.ndarray
    lo: np.ndarray
    cl: np.ndarray
    op: np.ndarray
    atr: np.ndarray
    # developing 15M at each 1M bar
    m15_dev_op: np.ndarray
    m15_dev_hi: np.ndarray
    m15_dev_lo: np.ndarray
    m15_dev_cl: np.ndarray
    # index of last completed native 15M bar (-1 if none)
    m15_completed_j: np.ndarray
    m15_bucket_j: np.ndarray
    # completed 15M series
    m15_native_cl: np.ndarray
    m15_native_hi: np.ndarray
    m15_native_lo: np.ndarray
    m15_native_op: np.ndarray
    m15_native_atr: np.ndarray


def build_m15_causal_arrays(m1: pd.DataFrame | None = None) -> M15CausalArrays:
    if m1 is None:
        m1 = load_market_1m_lw()
    m15 = resample_15m_causal(m1)
    idx = m1.index
    n = len(m1)
    g15 = idx.floor("15min")

    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float) if "atr" in m1.columns else np.full(n, 1.0)

    m15_dev_op = m1.groupby(g15)["open"].transform("first").values.astype(float)
    m15_dev_hi = m1.groupby(g15)["high"].cummax().values.astype(float)
    m15_dev_lo = m1.groupby(g15)["low"].cummin().values.astype(float)
    m15_dev_cl = cl.copy()

    mins = idx.minute.values
    offset = np.where(mins % 15 == 14, 0, 15)
    lab15 = g15 - pd.to_timedelta(offset, unit="m")
    m15_bucket_j = np.clip(m15.index.searchsorted(g15), 0, len(m15) - 1)
    comp_pos = m15.index.searchsorted(lab15, side="right") - 1
    m15_completed_j = comp_pos.astype(int)
    m15_completed_j[comp_pos < 0] = -1

    return M15CausalArrays(
        n=n,
        idx=idx,
        hi=hi,
        lo=lo,
        cl=cl,
        op=op,
        atr=atr,
        m15_dev_op=m15_dev_op,
        m15_dev_hi=m15_dev_hi,
        m15_dev_lo=m15_dev_lo,
        m15_dev_cl=m15_dev_cl,
        m15_completed_j=m15_completed_j,
        m15_bucket_j=m15_bucket_j,
        m15_native_cl=m15["close"].values.astype(float),
        m15_native_hi=m15["high"].values.astype(float),
        m15_native_lo=m15["low"].values.astype(float),
        m15_native_op=m15["open"].values.astype(float),
        m15_native_atr=m15["atr"].values.astype(float),
    )


class M15SequentialEngine:
    """Sequential 15M-only builder for prefix causality tests."""

    def __init__(self):
        self._start: pd.Timestamp | None = None
        self._o = self._h = self._l = self._c = np.nan
        self._completed = -1
        self._count = 0
        self.snapshots: list[dict] = []

    def on_bar(self, ts: pd.Timestamp, o: float, h: float, l: float, c: float) -> dict:
        b = _bucket_start(ts)
        if self._start != b:
            self._start = b
            self._o, self._h, self._l, self._c = o, h, l, c
            self._count += 1
        else:
            self._h = max(self._h, h)
            self._l = min(self._l, l)
            self._c = c
        if _is_bucket_close(ts):
            self._completed = self._count - 1
        snap = {
            "m15_o": self._o,
            "m15_h": self._h,
            "m15_l": self._l,
            "m15_c": self._c,
            "m15_completed_j": self._completed,
        }
        self.snapshots.append(snap)
        return snap
