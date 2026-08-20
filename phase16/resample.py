"""Exchange-session-aware intraday bar resampling."""

from __future__ import annotations

from typing import List

import pandas as pd


def cme_session_date(index: pd.DatetimeIndex) -> pd.Index:
    """Assign the CME trading date (the session opens at 18:00 CT)."""
    local_dates = index.normalize().tz_localize(None)
    after_open = index.hour >= 18
    return pd.Index(local_dates + pd.to_timedelta(after_open.astype(int), unit="D"))


def resample_ohlcv(
    frame: pd.DataFrame,
    minutes: int = 5,
    *,
    require_complete: bool = True,
) -> pd.DataFrame:
    """Resample smaller bars without spanning contract or session gaps.

    Input timestamps are bar-open times. With ``require_complete=True`` an
    incomplete 5-minute group is omitted instead of inventing missing minutes.
    """
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise TypeError("resampling requires a timezone-aware DatetimeIndex")
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    working = frame.copy()
    working["_session_date"] = cme_session_date(working.index).to_numpy()
    group_columns: List[str] = ["_session_date"]
    if "contract" in working.columns:
        group_columns.insert(0, "contract")
    pieces = []
    for _, group in working.groupby(group_columns, sort=True):
        bars = group[["open", "high", "low", "close", "volume"]].resample(
            f"{minutes}min", label="left", closed="left", origin="start_day"
        ).agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        counts = group["close"].resample(
            f"{minutes}min", label="left", closed="left", origin="start_day"
        ).count()
        bars = bars.dropna(subset=["open", "high", "low", "close"])
        if require_complete:
            bars = bars[counts.reindex(bars.index).fillna(0).astype(int) == minutes]
        if "contract" in group.columns and not group.empty:
            bars["contract"] = str(group["contract"].iloc[0])
        pieces.append(bars)
    if not pieces:
        columns = ["open", "high", "low", "close", "volume"]
        if "contract" in frame.columns:
            columns.append("contract")
        return pd.DataFrame(columns=columns, index=frame.index[:0])
    return pd.concat(pieces).sort_index()

