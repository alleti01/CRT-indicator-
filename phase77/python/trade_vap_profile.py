"""Causal TRUE_TRADE_VAP_PROFILE from trade prints — no backward fill."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any, Dict

import numpy as np
import pandas as pd

from .config import OPENING_RANGE_MINUTES, PROFILE_BIN_SIZE, PROFILE_TYPE, RTH_CLOSE, RTH_OPEN, TIMEZONE, VALUE_AREA_PCT


def _t(h: int, m: int) -> time:
    return time(h, m)


RTH_OPEN_T = _t(*RTH_OPEN)
RTH_CLOSE_T = _t(*RTH_CLOSE)


def is_rth(ts_et: pd.Timestamp) -> bool:
    t = ts_et.time()
    return RTH_OPEN_T <= t < RTH_CLOSE_T


def rth_session_date(ts_et: pd.Timestamp) -> date | None:
    return ts_et.date() if is_rth(ts_et) else None


def poc_vah_val(histogram: Dict[int, float]) -> tuple[float, float, float]:
    if not histogram:
        return np.nan, np.nan, np.nan
    bins = sorted(histogram.keys())
    vols = np.array([histogram[b] for b in bins], dtype=float)
    total = vols.sum()
    if total <= 0:
        return np.nan, np.nan, np.nan
    poc_i = int(np.argmax(vols))
    poc = (bins[poc_i] + 0.5) * PROFILE_BIN_SIZE
    lo_i = hi_i = poc_i
    captured = vols[poc_i]
    while captured / total < VALUE_AREA_PCT and (lo_i > 0 or hi_i < len(bins) - 1):
        vb = vols[lo_i - 1] if lo_i > 0 else -1.0
        va = vols[hi_i + 1] if hi_i < len(bins) - 1 else -1.0
        if vb >= va and lo_i > 0:
            lo_i -= 1
            captured += vols[lo_i]
        elif hi_i < len(bins) - 1:
            hi_i += 1
            captured += vols[hi_i]
        elif lo_i > 0:
            lo_i -= 1
            captured += vols[lo_i]
        else:
            break
    val = (bins[lo_i] + 0.5) * PROFILE_BIN_SIZE
    vah = (bins[hi_i] + 0.5) * PROFILE_BIN_SIZE
    return poc, vah, val


def hvn_lvn_bins(histogram: Dict[int, float]) -> tuple[set[int], set[int]]:
    if len(histogram) < 3:
        return set(), set()
    vols = np.array(list(histogram.values()), dtype=float)
    pos = vols[vols > 0]
    if len(pos) < 3:
        return set(), set()
    hvn_cut = np.quantile(pos, 0.80)
    lvn_cut = np.quantile(pos, 0.20)
    hvn = {b for b, v in histogram.items() if v >= hvn_cut}
    lvn = {b for b, v in histogram.items() if v <= lvn_cut and v > 0}
    return hvn, lvn


@dataclass
class SessionSnap:
    session_date: date
    high: float
    low: float
    close: float
    vwap: float
    poc: float
    vah: float
    val: float
    volume: float
    profile_type: str


@dataclass
class DevSession:
    session_date: date
    high: float = -np.inf
    low: float = np.inf
    close: float = np.nan
    cum_pv: float = 0.0
    cum_vol: float = 0.0
    histogram: Dict[int, float] = field(default_factory=dict)
    or_high: float = np.nan
    or_low: float = np.nan
    or_done: bool = False

    def add_trade(self, price: float, size: float) -> None:
        b = int(np.floor(price / PROFILE_BIN_SIZE))
        self.histogram[b] = self.histogram.get(b, 0.0) + size
        self.cum_pv += price * size
        self.cum_vol += size
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price

    def update_bar(self, h: float, l: float, c: float, vol: float, ts_et: pd.Timestamp) -> None:
        self.high = max(self.high, h)
        self.low = min(self.low, l)
        self.close = c
        if vol > 0:
            tp = (h + l + c) / 3.0
            self.cum_pv += tp * vol
            self.cum_vol += vol
        if not self.or_done:
            open_ts = pd.Timestamp(datetime.combine(self.session_date, RTH_OPEN_T), tz=TIMEZONE)
            or_end = open_ts + pd.Timedelta(minutes=OPENING_RANGE_MINUTES)
            if ts_et < or_end:
                self.or_high = h if np.isnan(self.or_high) else max(self.or_high, h)
                self.or_low = l if np.isnan(self.or_low) else min(self.or_low, l)
            else:
                self.or_done = True

    @property
    def vwap(self) -> float:
        return self.cum_pv / self.cum_vol if self.cum_vol > 0 else np.nan

    def snapshot(self) -> SessionSnap:
        poc, vah, val = poc_vah_val(self.histogram)
        return SessionSnap(
            session_date=self.session_date,
            high=self.high,
            low=self.low,
            close=self.close,
            vwap=self.vwap,
            poc=poc,
            vah=vah,
            val=val,
            volume=self.cum_vol,
            profile_type=PROFILE_TYPE,
        )


def build_causal_profile_features(m1: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Bar-by-bar profile + session refs from trades known_at <= bar close."""
    ts_ns = trades["ts_local"].astype("int64").to_numpy()
    prices = trades["price"].to_numpy()
    sizes = trades["size"].to_numpy()

    prior: SessionSnap | None = None
    dev: DevSession | None = None
    last_sd: date | None = None
    trade_ptr = 0

    cols: dict[str, list[Any]] = {k: [] for k in (
        "in_rth", "session_date", "profile_type",
        "prior_vah", "prior_val", "prior_poc", "prior_high", "prior_low", "prior_vwap",
        "dev_vah", "dev_val", "dev_poc", "dev_vwap", "dev_high", "dev_low",
        "or_high", "or_low", "in_hvn", "in_lvn",
        "roll_high_5", "roll_low_5", "roll_high_10", "roll_low_10",
        "roll_high_20", "roll_low_20", "roll_high_30", "roll_low_30",
    )}

    roll_h5 = m1["high"].rolling(5, min_periods=1).max().values
    roll_l5 = m1["low"].rolling(5, min_periods=1).min().values
    roll_h10 = m1["high"].rolling(10, min_periods=1).max().values
    roll_l10 = m1["low"].rolling(10, min_periods=1).min().values
    roll_h20 = m1["high"].rolling(20, min_periods=1).max().values
    roll_l20 = m1["low"].rolling(20, min_periods=1).min().values
    roll_h30 = m1["high"].rolling(30, min_periods=1).max().values
    roll_l30 = m1["low"].rolling(30, min_periods=1).min().values

    for i, (bar_ts, row) in enumerate(m1.iterrows()):
        ts_et = row["ts_et"]
        bar_ns = int(bar_ts.value)
        in_r = is_rth(ts_et)
        sd = rth_session_date(ts_et)

        while trade_ptr < len(ts_ns) and ts_ns[trade_ptr] <= bar_ns:
            t_et = trades.iloc[trade_ptr]["ts_local"]
            if is_rth(t_et):
                tsd = rth_session_date(t_et)
                if tsd is not None and (dev is None or dev.session_date != tsd):
                    if dev is not None and last_sd is not None and tsd != last_sd:
                        prior = dev.snapshot()
                    dev = DevSession(session_date=tsd)
                    last_sd = tsd
                if dev is not None:
                    dev.add_trade(float(prices[trade_ptr]), float(sizes[trade_ptr]))
            trade_ptr += 1

        if sd is not None and (dev is None or dev.session_date != sd):
            if dev is not None and last_sd is not None and sd != last_sd:
                prior = dev.snapshot()
            dev = DevSession(session_date=sd)
            last_sd = sd

        if dev is not None and in_r:
            dev.update_bar(row["high"], row["low"], row["close"], row["volume"], ts_et)

        poc = vah = val = vwap = np.nan
        in_hvn = in_lvn = False
        if dev is not None and in_r and dev.histogram:
            poc, vah, val = poc_vah_val(dev.histogram)
            vwap = dev.vwap
            hvn, lvn = hvn_lvn_bins(dev.histogram)
            b = int(np.floor(row["close"] / PROFILE_BIN_SIZE))
            in_hvn = b in hvn
            in_lvn = b in lvn

        def _p(attr: str) -> float:
            return getattr(prior, attr) if prior else np.nan

        cols["in_rth"].append(in_r)
        cols["session_date"].append(str(sd) if sd else "")
        cols["profile_type"].append(PROFILE_TYPE)
        cols["prior_vah"].append(_p("vah"))
        cols["prior_val"].append(_p("val"))
        cols["prior_poc"].append(_p("poc"))
        cols["prior_high"].append(_p("high"))
        cols["prior_low"].append(_p("low"))
        cols["prior_vwap"].append(_p("vwap"))
        cols["dev_vah"].append(vah if in_r else np.nan)
        cols["dev_val"].append(val if in_r else np.nan)
        cols["dev_poc"].append(poc if in_r else np.nan)
        cols["dev_vwap"].append(vwap if in_r else np.nan)
        cols["dev_high"].append(dev.high if dev and in_r else np.nan)
        cols["dev_low"].append(dev.low if dev and in_r else np.nan)
        cols["or_high"].append(dev.or_high if dev and in_r else np.nan)
        cols["or_low"].append(dev.or_low if dev and in_r else np.nan)
        cols["in_hvn"].append(in_hvn)
        cols["in_lvn"].append(in_lvn)
        cols["roll_high_5"].append(roll_h5[i])
        cols["roll_low_5"].append(roll_l5[i])
        cols["roll_high_10"].append(roll_h10[i])
        cols["roll_low_10"].append(roll_l10[i])
        cols["roll_high_20"].append(roll_h20[i])
        cols["roll_low_20"].append(roll_l20[i])
        cols["roll_high_30"].append(roll_h30[i])
        cols["roll_low_30"].append(roll_l30[i])

    feat = pd.DataFrame(cols, index=m1.index)
    return pd.concat([m1, feat], axis=1)
