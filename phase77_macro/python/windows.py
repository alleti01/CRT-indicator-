"""Macro window tagging — T-15 through T+60 (frozen)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MACRO_POST_MINUTES, MACRO_PRE_MINUTES, SUBWINDOWS


def tag_macro_windows(
    bar_index: pd.DatetimeIndex,
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """
    Tag each bar with macro window membership.
    Returns DataFrame indexed like bar_index with columns:
    in_macro, event_name, event_group, minutes_from_release, subwindow
    """
    n = len(bar_index)
    in_macro = np.zeros(n, dtype=bool)
    event_name = [""] * n
    event_group = [""] * n
    minutes_from = np.full(n, np.nan)
    subwindow = [""] * n

    # bar_index should be UTC
    bars = pd.Series(range(n), index=bar_index)

    for _, ev in calendar.iterrows():
        t0 = ev["release_ts_utc"]
        start = t0 - pd.Timedelta(minutes=MACRO_PRE_MINUTES)
        end = t0 + pd.Timedelta(minutes=MACRO_POST_MINUTES)
        mask = (bar_index >= start) & (bar_index <= end)
        idxs = np.where(mask)[0]
        for i in idxs:
            in_macro[i] = True
            event_name[i] = ev["event_name"]
            event_group[i] = ev["event_group"]
            mins = (bar_index[i] - t0).total_seconds() / 60.0
            minutes_from[i] = mins
            for sw_name, lo, hi in SUBWINDOWS:
                if lo <= mins < hi or (hi == 0 and lo <= mins <= 0):
                    if lo <= mins < hi or (sw_name == "PRE" and -MACRO_PRE_MINUTES <= mins < 0):
                        subwindow[i] = sw_name
                        break
            # fix PRE boundary
            if -MACRO_PRE_MINUTES <= mins < 0:
                subwindow[i] = "PRE"
            elif 0 <= mins < 5:
                subwindow[i] = "IMMEDIATE"
            elif 5 <= mins < 15:
                subwindow[i] = "EARLY"
            elif 15 <= mins < 30:
                subwindow[i] = "DEVELOPMENT"
            elif 30 <= mins <= MACRO_POST_MINUTES:
                subwindow[i] = "LATE"

    return pd.DataFrame({
        "in_macro": in_macro,
        "event_name": event_name,
        "event_group": event_group,
        "minutes_from_release": minutes_from,
        "subwindow": subwindow,
    }, index=bar_index)


def same_time_control_mask(
    bar_index: pd.DatetimeIndex,
    calendar: pd.DataFrame,
    macro_tags: pd.DataFrame,
) -> pd.Series:
    """
    Bars at same clock time (NY) as tier-1 releases but NOT on macro event days/windows.
    """
    ts_ny = bar_index.tz_convert("America/New_York")
    macro_dates = set(calendar["release_date"].unique())
    # Collect (hour, minute) slots from tier-1 releases
    slots = set()
    for _, ev in calendar.iterrows():
        t_ny = ev["release_ts_ny"]
        for delta in range(-MACRO_PRE_MINUTES, MACRO_POST_MINUTES + 1):
            slot_ts = t_ny + pd.Timedelta(minutes=delta)
            slots.add((slot_ts.hour, slot_ts.minute))

    mask = pd.Series(False, index=bar_index)
    for i, t in enumerate(ts_ny):
        if (t.hour, t.minute) in slots and str(t.date()) not in macro_dates:
            mask.iloc[i] = True
    # Exclude any bar already in macro window
    mask &= ~macro_tags["in_macro"]
    return mask


def ordinary_baseline_mask(macro_tags: pd.DataFrame, same_time: pd.Series, in_rth: pd.Series) -> pd.Series:
    return in_rth & ~macro_tags["in_macro"] & ~same_time
