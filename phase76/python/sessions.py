"""Session calendar and overnight references — causal only."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Dict

import numpy as np
import pandas as pd

from .config import OPENING_RANGE_MINUTES, OVERNIGHT_START, RTH_CLOSE, RTH_OPEN, TIMEZONE


def _t(h: int, m: int) -> time:
    return time(h, m)


RTH_OPEN_T = _t(*RTH_OPEN)
RTH_CLOSE_T = _t(*RTH_CLOSE)
OVERNIGHT_START_T = _t(*OVERNIGHT_START)


def is_rth(ts_et: pd.Timestamp) -> bool:
    t = ts_et.time()
    return RTH_OPEN_T <= t < RTH_CLOSE_T


def rth_session_date(ts_et: pd.Timestamp) -> date | None:
    """Calendar date of RTH session; None if outside RTH."""
    if not is_rth(ts_et):
        return None
    return ts_et.date()


def overnight_key(ts_et: pd.Timestamp) -> date:
    """Overnight window ending on this RTH date (18:00 prior → 09:29 current)."""
    d = ts_et.date()
    if ts_et.time() >= OVERNIGHT_START_T:
        return (ts_et + pd.Timedelta(days=1)).date()
    return d


@dataclass
class SessionSnapshot:
    """Frozen completed RTH session auction summary."""

    session_date: date
    high: float
    low: float
    close: float
    vwap: float
    poc: float
    vah: float
    val: float
    value_width: float
    volume: float
    profile_type: str


@dataclass
class DevelopingSession:
    session_date: date
    high: float = -np.inf
    low: float = np.inf
    close: float = np.nan
    cum_pv: float = 0.0
    cum_vol: float = 0.0
    histogram: Dict[int, float] = field(default_factory=dict)
    bar_count: int = 0
    or_high: float = np.nan
    or_low: float = np.nan
    or_done: bool = False

    def update_bar(self, o: float, h: float, l: float, c: float, vol: float, ts_et: pd.Timestamp, *, bin_size: float) -> None:
        self.bar_count += 1
        self.high = max(self.high, h)
        self.low = min(self.low, l)
        self.close = c
        tp = (h + l + c) / 3.0
        self.cum_pv += tp * vol
        self.cum_vol += vol
        lo_bin = int(np.floor(l / bin_size))
        hi_bin = int(np.floor(h / bin_size))
        n_bins = max(hi_bin - lo_bin + 1, 1)
        w = vol / n_bins
        for b in range(lo_bin, hi_bin + 1):
            self.histogram[b] = self.histogram.get(b, 0.0) + w

        if not self.or_done:
            open_dt = datetime.combine(self.session_date, RTH_OPEN_T)
            open_ts = pd.Timestamp(open_dt, tz=TIMEZONE)
            or_end = open_ts + pd.Timedelta(minutes=OPENING_RANGE_MINUTES)
            if ts_et < or_end:
                self.or_high = h if np.isnan(self.or_high) else max(self.or_high, h)
                self.or_low = l if np.isnan(self.or_low) else min(self.or_low, l)
            else:
                self.or_done = True

    @property
    def vwap(self) -> float:
        return self.cum_pv / self.cum_vol if self.cum_vol > 0 else np.nan

    def to_snapshot(self, profile_type: str) -> SessionSnapshot:
        from .profile import poc_vah_val_from_hist

        poc, vah, val = poc_vah_val_from_hist(self.histogram)
        return SessionSnapshot(
            session_date=self.session_date,
            high=self.high,
            low=self.low,
            close=self.close,
            vwap=self.vwap,
            poc=poc,
            vah=vah,
            val=val,
            value_width=vah - val if not (np.isnan(vah) or np.isnan(val)) else np.nan,
            volume=self.cum_vol,
            profile_type=profile_type,
        )


@dataclass
class OvernightTracker:
    """Tracks high/low for globex overnight window causally."""

    current_key: date | None = None
    high: float = -np.inf
    low: float = np.inf

    def update(self, ts_et: pd.Timestamp, h: float, l: float) -> tuple[float, float]:
        key = overnight_key(ts_et)
        t = ts_et.time()
        in_overnight = (t >= OVERNIGHT_START_T) or (t < RTH_OPEN_T)
        if not in_overnight:
            return np.nan, np.nan
        if self.current_key != key:
            self.current_key = key
            self.high = h
            self.low = l
        else:
            self.high = max(self.high, h)
            self.low = min(self.low, l)
        return self.high, self.low
