"""Phase60 — strictly causal developing 5M / 15M HTF construction.

Semantics (Task 1):
- At 1M timestamp t, only data from timestamps <= t may contribute.
- Developing bucket OHLC resets at each new HTF period start.
- Completed buckets append to history only after the final 1M bar of the period closes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class DevelopingHTFSpec:
    """Explicit Phase60 CAUSAL B semantics."""

    name: str = "causal_b_developing"
    m5_minutes: int = 5
    m15_minutes: int = 15
    rule: str = "At 1M close t: O=first open of bucket; H=max high; L=min low; C=current close"


@dataclass
class DevelopingHTFArrays:
    """Per-1M aligned developing HTF + completed indices for causal feature access."""

    m1_index: pd.DatetimeIndex
    # Developing OHLC at each 1M bar (causal)
    m5_dev_op: np.ndarray
    m5_dev_hi: np.ndarray
    m5_dev_lo: np.ndarray
    m5_dev_cl: np.ndarray
    m15_dev_op: np.ndarray
    m15_dev_hi: np.ndarray
    m15_dev_lo: np.ndarray
    m15_dev_cl: np.ndarray
    # Index of last *completed* native 5M/15M bar at each 1M bar (-1 if none)
    m5_completed_j: np.ndarray
    m15_completed_j: np.ndarray
    # Index label of current developing bucket on native HTF grid
    m5_bucket_j: np.ndarray
    m15_bucket_j: np.ndarray
    # Source timestamp audit: max 1M ts used for developing OHLC (= decision ts)
    source_ts_ms: np.ndarray = field(repr=False)


def _bucket_start(ts: pd.Timestamp, minutes: int) -> pd.Timestamp:
    return ts.floor(f"{minutes}min")


def _is_bucket_close(ts: pd.Timestamp, minutes: int) -> bool:
    return ts.minute % minutes == (minutes - 1)


def build_developing_htf_vectorized(
    m1: pd.DataFrame,
    m5_index: pd.DatetimeIndex,
    m15_index: pd.DatetimeIndex,
) -> DevelopingHTFArrays:
    """Vectorized build — equivalent to sequential DevelopingHTFEngine."""
    idx = m1.index
    n = len(m1)

    g5 = idx.floor("5min")
    g15 = idx.floor("15min")

    m5_dev_op = m1.groupby(g5)["open"].transform("first").values.astype(float)
    m5_dev_hi = m1.groupby(g5)["high"].cummax().values.astype(float)
    m5_dev_lo = m1.groupby(g5)["low"].cummin().values.astype(float)
    m5_dev_cl = m1["close"].values.astype(float)

    m15_dev_op = m1.groupby(g15)["open"].transform("first").values.astype(float)
    m15_dev_hi = m1.groupby(g15)["high"].cummax().values.astype(float)
    m15_dev_lo = m1.groupby(g15)["low"].cummin().values.astype(float)
    m15_dev_cl = m1["close"].values.astype(float)

    # Completed index: last fully closed HTF bar at each 1M close
    m5_completed_j = np.full(n, -1, dtype=int)
    m15_completed_j = np.full(n, -1, dtype=int)
    m5_bucket_j = np.zeros(n, dtype=int)
    m15_bucket_j = np.zeros(n, dtype=int)

    m5_pos = {t: i for i, t in enumerate(m5_index)}
    m15_pos = {t: i for i, t in enumerate(m15_index)}

    for i, ts in enumerate(idx):
        b5 = _bucket_start(ts, 5)
        b15 = _bucket_start(ts, 15)
        m5_bucket_j[i] = m5_pos.get(b5, 0)
        m15_bucket_j[i] = m15_pos.get(b15, 0)

        if _is_bucket_close(ts, 5):
            lab5 = b5
        else:
            lab5 = b5 - pd.Timedelta(minutes=5)
        if _is_bucket_close(ts, 15):
            lab15 = b15
        else:
            lab15 = b15 - pd.Timedelta(minutes=15)

        if lab5 in m5_pos:
            m5_completed_j[i] = m5_pos[lab5]
        elif m5_index.searchsorted(lab5, side="right") > 0:
            m5_completed_j[i] = int(m5_index.searchsorted(lab5, side="right") - 1)

        if lab15 in m15_pos:
            m15_completed_j[i] = m15_pos[lab15]
        elif m15_index.searchsorted(lab15, side="right") > 0:
            m15_completed_j[i] = int(m15_index.searchsorted(lab15, side="right") - 1)

    source_ms = (idx.astype("int64") // 10**6).values
    return DevelopingHTFArrays(
        m1_index=idx,
        m5_dev_op=m5_dev_op,
        m5_dev_hi=m5_dev_hi,
        m5_dev_lo=m5_dev_lo,
        m5_dev_cl=m5_dev_cl,
        m15_dev_op=m15_dev_op,
        m15_dev_hi=m15_dev_hi,
        m15_dev_lo=m15_dev_lo,
        m15_dev_cl=m15_dev_cl,
        m5_completed_j=m5_completed_j,
        m15_completed_j=m15_completed_j,
        m5_bucket_j=m5_bucket_j,
        m15_bucket_j=m15_bucket_j,
        source_ts_ms=source_ms,
    )


class DevelopingHTFEngine:
    """Sequential incremental builder for causality tests."""

    def __init__(self, m5_minutes: int = 5, m15_minutes: int = 15):
        self.m5_minutes = m5_minutes
        self.m15_minutes = m15_minutes
        self._m5_start: pd.Timestamp | None = None
        self._m15_start: pd.Timestamp | None = None
        self._m5_o = self._m5_h = self._m5_l = self._m5_c = np.nan
        self._m15_o = self._m15_h = self._m15_l = self._m15_c = np.nan
        self._m5_completed = -1
        self._m15_completed = -1
        self._m5_count = 0
        self._m15_count = 0
        self.snapshots: list[dict] = []

    def on_bar(self, ts: pd.Timestamp, o: float, h: float, l: float, c: float) -> dict:
        b5 = _bucket_start(ts, self.m5_minutes)
        b15 = _bucket_start(ts, self.m15_minutes)

        if self._m5_start != b5:
            if self._m5_start is not None and _is_bucket_close(ts - pd.Timedelta(minutes=1), self.m5_minutes):
                self._m5_completed = self._m5_count
            self._m5_start = b5
            self._m5_o, self._m5_h, self._m5_l, self._m5_c = o, h, l, c
            self._m5_count += 1
        else:
            self._m5_h = max(self._m5_h, h)
            self._m5_l = min(self._m5_l, l)
            self._m5_c = c

        if self._m15_start != b15:
            self._m15_start = b15
            self._m15_o, self._m15_h, self._m15_l, self._m15_c = o, h, l, c
            self._m15_count += 1
        else:
            self._m15_h = max(self._m15_h, h)
            self._m15_l = min(self._m15_l, l)
            self._m15_c = c

        if _is_bucket_close(ts, self.m5_minutes):
            self._m5_completed = self._m5_count - 1
        if _is_bucket_close(ts, self.m15_minutes):
            self._m15_completed = self._m15_count - 1

        snap = {
            "ts": ts,
            "m5_o": self._m5_o,
            "m5_h": self._m5_h,
            "m5_l": self._m5_l,
            "m5_c": self._m5_c,
            "m15_o": self._m15_o,
            "m15_h": self._m15_h,
            "m15_l": self._m15_l,
            "m15_c": self._m15_c,
            "m5_completed_j": self._m5_completed,
            "m15_completed_j": self._m15_completed,
            "max_source_ts": ts,
        }
        self.snapshots.append(snap)
        return snap
