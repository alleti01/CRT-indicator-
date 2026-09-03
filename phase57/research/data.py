"""Thin wrapper around Phase53 data loading for Phase57."""

from __future__ import annotations

import pandas as pd

from phase53.research.data import (
    align_htf_to_1m,
    htf_bar_index,
    load_markets,
    resample_5m_causal,
)
from phase53.research.metrics import max_dd, pf, summarize_r
from phase45.execution.data_1m import cost_r
from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase57.config import TIMEZONE


def load_phase57_markets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load m1, m5, m15 using identical Phase53 pipeline."""
    return load_markets()


def session_minute(ts: pd.Timestamp) -> int:
    """Minutes since 08:30 CT for a given timestamp."""
    base = ts.normalize() + pd.Timedelta(hours=8, minutes=30)
    return int((ts - base).total_seconds() / 60)


def time_bucket(ts: pd.Timestamp) -> str:
    """Map timestamp to CT session bucket."""
    t = ts.time()
    from phase57.config import SESSION_BUCKETS
    for label, (start, end) in SESSION_BUCKETS.items():
        sh, sm = map(int, start.split(":"))
        eh, em = map(int, end.split(":"))
        from datetime import time as dtime
        if dtime(sh, sm) <= t < dtime(eh, em):
            return label
    return "other"


__all__ = [
    "load_phase57_markets",
    "align_htf_to_1m",
    "htf_bar_index",
    "resample_5m_causal",
    "cost_r",
    "summarize_r",
    "pf",
    "max_dd",
    "precompute_swing_highs",
    "precompute_swing_lows",
    "precompute_last2_swing_highs",
    "precompute_last2_swing_lows",
    "session_minute",
    "time_bucket",
]
