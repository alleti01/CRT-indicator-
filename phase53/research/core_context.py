"""CORE / Phase44 context — vectorized."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.config import B1_WINDOW_MIN, CORE_OVERLAP_MIN, P44_SIGNALS, P45_WF


def build_p44_state(m1: pd.DataFrame, m15: pd.DataFrame) -> pd.Series:
    sig = pd.read_csv(P44_SIGNALS, parse_dates=["timestamp"])
    sig["timestamp"] = pd.to_datetime(sig["timestamp"], utc=True).dt.tz_convert(m1.index.tz)
    accepted = sig.loc[sig["accepted"] == True].copy()  # noqa: E712
    state = pd.Series("NONE", index=m15.index, dtype=object)
    for _, row in accepted.iterrows():
        ts = row["timestamp"]
        loc = state.index.searchsorted(ts)
        if loc < len(state):
            state.iloc[loc:] = row["direction"].upper()
    return state.reindex(m1.index, method="ffill").fillna("NONE")


def build_core_context(m1: pd.DataFrame) -> pd.DataFrame:
    n = len(m1)
    b1_active = np.zeros(n, dtype=np.int8)
    core_auth = np.zeros(n, dtype=np.int8)
    min_since_p44 = np.full(n, np.nan)
    min_since_core = np.full(n, np.nan)

    p44 = pd.read_csv(P45_WF, parse_dates=["actionable_timestamp"])
    p44["actionable_timestamp"] = pd.to_datetime(p44["actionable_timestamp"], utc=True).dt.tz_convert(m1.index.tz)
    for _, row in p44.iterrows():
        act = pd.Timestamp(row["actionable_timestamp"])
        end = act + pd.Timedelta(minutes=B1_WINDOW_MIN)
        i0 = int(m1.index.searchsorted(act, side="left"))
        i1 = int(m1.index.searchsorted(end, side="right"))
        b1_active[i0:i1] = 1

    from phase48.entries import load_frozen_entries

    core = load_frozen_entries()
    for ets in pd.to_datetime(core["entry_timestamp"]):
        i0 = int(m1.index.searchsorted(ets, side="left"))
        i1 = min(n, i0 + CORE_OVERLAP_MIN + 1)
        core_auth[i0:i1] = 1

    last_p44_i = -1
    for i, ts in enumerate(m1.index):
        if last_p44_i >= 0:
            min_since_p44[i] = (ts - m1.index[last_p44_i]).total_seconds() / 60.0
        if p44["actionable_timestamp"].eq(ts).any():
            last_p44_i = i

    last_core_i = -1
    core_ts = pd.to_datetime(core["entry_timestamp"]).sort_values().values
    core_idx = np.searchsorted(m1.index.values, core_ts, side="left")
    core_bar_set = set(int(i) for i in core_idx if i < n)
    for i, ts in enumerate(m1.index):
        if last_core_i >= 0:
            min_since_core[i] = (ts - m1.index[last_core_i]).total_seconds() / 60.0
        if i in core_bar_set:
            last_core_i = i

    return pd.DataFrame(
        {
            "b1_active": b1_active,
            "core_authorized": core_auth,
            "min_since_p44": min_since_p44,
            "min_since_core_entry": min_since_core,
        },
        index=range(n),
    )
