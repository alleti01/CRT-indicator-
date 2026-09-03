"""Resample forward 1m bars to 5m and 15m using project conventions."""

from __future__ import annotations

import pandas as pd

from phase16.resample import resample_ohlcv
from phase28.resample_timeframes import aggregate_from_5m


def resample_1m_to_5m(frame_1m: pd.DataFrame) -> pd.DataFrame:
    cols = ["open", "high", "low", "close", "volume"]
    working = frame_1m[cols].sort_index().copy()
    if "contract" in frame_1m.columns:
        working["contract"] = frame_1m["contract"]
    return resample_ohlcv(working, minutes=5, require_complete=True)


def resample_5m_to_15m(frame_5m: pd.DataFrame) -> pd.DataFrame:
    return aggregate_from_5m(frame_5m.sort_index(), 15)


def resample_1m_to_15m(frame_1m: pd.DataFrame) -> pd.DataFrame:
    return resample_5m_to_15m(resample_1m_to_5m(frame_1m))


def verify_15m_against_1m(bars_15m: pd.DataFrame, bars_1m: pd.DataFrame) -> list[str]:
    """Verify each 15m bar matches its underlying 1m aggregation."""
    issues: list[str] = []
    if bars_15m.empty:
        return issues
    for ts, bar in bars_15m.iterrows():
        end = ts + pd.Timedelta(minutes=15)
        chunk = bars_1m.loc[(bars_1m.index >= ts) & (bars_1m.index < end)]
        if chunk.empty:
            issues.append(f"missing_1m_for_15m_bar_{ts}")
            continue
        if abs(float(bar.open) - float(chunk.iloc[0].open)) > 1e-6:
            issues.append(f"open_mismatch_{ts}")
        if abs(float(bar.high) - float(chunk["high"].max())) > 1e-6:
            issues.append(f"high_mismatch_{ts}")
        if abs(float(bar.low) - float(chunk["low"].min())) > 1e-6:
            issues.append(f"low_mismatch_{ts}")
        if abs(float(bar.close) - float(chunk.iloc[-1].close)) > 1e-6:
            issues.append(f"close_mismatch_{ts}")
    return issues
