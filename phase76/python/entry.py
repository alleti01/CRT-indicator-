"""Executable entry semantics — signal on close T, entry open T+1."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import ENTRY_DELAY_BARS


@dataclass
class SignalRecord:
    signal_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    direction: str  # LONG | SHORT
    entry_price: float
    signal_price: float
    delay_bars: int
    level_price: float
    dist_from_level: float
    chase_atr: float
    atr: float
    reason_codes: str
    family: str
    value_source: str


def attach_entries(signals: pd.DataFrame, ohlc: pd.DataFrame) -> pd.DataFrame:
    """Add entry_ts, entry_price, chase_atr from next-bar open."""
    if signals.empty:
        return signals
    out = signals.copy()
    entries_ts = []
    entries_px = []
    chase = []
    for ts in out["signal_ts"]:
        loc = ohlc.index.get_loc(ts)
        entry_i = loc + ENTRY_DELAY_BARS
        if entry_i >= len(ohlc):
            entries_ts.append(pd.NaT)
            entries_px.append(np.nan)
            chase.append(np.nan)
            continue
        entry_ts = ohlc.index[entry_i]
        entry_px = float(ohlc.iloc[entry_i]["open"])
        sig_px = float(ohlc.loc[ts, "close"])
        atr = float(ohlc.loc[ts, "atr"]) if pd.notna(ohlc.loc[ts, "atr"]) else np.nan
        entries_ts.append(entry_ts)
        entries_px.append(entry_px)
        chase.append(abs(entry_px - sig_px) / atr if atr and atr > 0 else np.nan)
    out["entry_ts"] = entries_ts
    out["entry_price"] = entries_px
    out["chase_atr"] = chase
    out["delay_bars"] = ENTRY_DELAY_BARS
    return out
