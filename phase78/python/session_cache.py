"""Precomputed session / overnight levels by ET date."""
from __future__ import annotations

from datetime import date, time

import numpy as np
import pandas as pd

RTH_OPEN_T = time(9, 30)
RTH_CLOSE_T = time(16, 0)
OVERNIGHT_EVENING_T = time(18, 0)


def add_intraday_cumulative(df: pd.DataFrame) -> pd.DataFrame:
    d = df["ts_et"].dt.date
    df = df.copy()
    df["_day_code"] = pd.factorize(d, sort=False)[0]
    df["day_high_so_far"] = df.groupby("_day_code", sort=False)["high"].cummax()
    df["day_low_so_far"] = df.groupby("_day_code", sort=False)["low"].cummin()
    return df


def build_session_cache(df: pd.DataFrame) -> dict:
    ts_et = df["ts_et"]
    day_codes = df["_day_code"].values
    cache: dict = {
        "rth_high": {},
        "rth_low": {},
        "overnight_high": {},
        "overnight_low": {},
        "day_first_idx": {},
    }
    tm = ts_et.dt.time.values
    high = df["high"].values
    low = df["low"].values
    for code in np.unique(day_codes):
        idx = np.flatnonzero(day_codes == code)
        day = ts_et.iloc[idx[0]].date()
        cache["day_first_idx"][day] = int(idx[0])
        rm = (tm[idx] >= RTH_OPEN_T) & (tm[idx] < RTH_CLOSE_T)
        if rm.any():
            ri = idx[rm]
            cache["rth_high"][day] = float(high[ri].max())
            cache["rth_low"][day] = float(low[ri].min())
        om = (tm[idx] < RTH_OPEN_T) | (tm[idx] >= OVERNIGHT_EVENING_T)
        if om.any():
            oi = idx[om]
            cache["overnight_high"][day] = float(high[oi].max())
            cache["overnight_low"][day] = float(low[oi].min())
    return cache


def session_levels_cached(
    df: pd.DataFrame,
    window_start_utc: pd.Timestamp,
    calendar_date: date,
    cache: dict,
) -> list[tuple[str, str, float]]:
    levels: list[tuple[str, str, float]] = []
    rth_days = sorted(cache["rth_high"].keys())
    prior = [d for d in rth_days if d < calendar_date]
    if prior:
        pd_ = prior[-1]
        levels.append(("PRIOR_SESSION_HIGH", "BUY_SIDE", cache["rth_high"][pd_]))
        levels.append(("PRIOR_SESSION_LOW", "SELL_SIDE", cache["rth_low"][pd_]))
    if calendar_date in cache.get("overnight_high", {}):
        levels.append(("OVERNIGHT_HIGH", "BUY_SIDE", cache["overnight_high"][calendar_date]))
        levels.append(("OVERNIGHT_LOW", "SELL_SIDE", cache["overnight_low"][calendar_date]))
    if calendar_date not in cache.get("day_first_idx", {}):
        return levels
    end_idx = int(df.index.searchsorted(window_start_utc)) - 1
    start_idx = cache["day_first_idx"][calendar_date]
    if end_idx >= start_idx:
        levels.append(("SESSION_HIGH_PRE_WINDOW", "BUY_SIDE", float(df["day_high_so_far"].iat[end_idx])))
        levels.append(("SESSION_LOW_PRE_WINDOW", "SELL_SIDE", float(df["day_low_so_far"].iat[end_idx])))
    return levels
