"""Opportunity memory — deduplicate repeated Phase72A events."""
from __future__ import annotations

import pandas as pd

from phase84.python.config import OPPORTUNITY_GAP_BARS


def dedupe_opportunities(signals: pd.DataFrame, gap_bars: int = OPPORTUNITY_GAP_BARS) -> pd.DataFrame:
    """Keep first signal in each cluster separated by at least gap_bars."""
    if signals.empty or "signal_i" not in signals.columns:
        return signals
    out = signals.sort_values("phase72a_signal_time").reset_index(drop=True)
    kept: list[int] = []
    last_i = -10**9
    for i, row in out.iterrows():
        si = int(row["signal_i"])
        if si - last_i >= gap_bars:
            kept.append(i)
            last_i = si
    return out.iloc[kept].reset_index(drop=True)
