"""Causal aggregation of validated 5m NQ bars to higher timeframes."""

from __future__ import annotations

import pandas as pd

from phase16.resample import cme_session_date


def aggregate_from_5m(frame: pd.DataFrame, target_minutes: int) -> pd.DataFrame:
    if target_minutes == 5:
        return frame.sort_index().copy()
    if target_minutes % 5 != 0:
        raise ValueError("target minutes must be a multiple of 5")
    ratio = target_minutes // 5
    working = frame.sort_index().copy()
    working["_session_date"] = cme_session_date(working.index).to_numpy()
    group_cols = ["_session_date"]
    if "contract" in working.columns:
        group_cols.insert(0, "contract")
    pieces = []
    for _, group in working.groupby(group_cols, sort=True):
        bars = group[["open", "high", "low", "close", "volume"]].resample(
            f"{target_minutes}min", label="left", closed="left", origin="start_day"
        ).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        counts = group["close"].resample(
            f"{target_minutes}min", label="left", closed="left", origin="start_day"
        ).count()
        bars = bars.dropna(subset=["open", "high", "low", "close"])
        bars = bars[counts.reindex(bars.index).fillna(0).astype(int) >= ratio]
        if "contract" in group.columns and not group.empty:
            bars["contract"] = str(group["contract"].iloc[0])
        pieces.append(bars)
    if not pieces:
        return frame.iloc[:0].copy()
    return pd.concat(pieces).sort_index()
