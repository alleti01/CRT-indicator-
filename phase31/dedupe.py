"""Causal signal deduplication for Phase 31."""

from __future__ import annotations

from typing import Optional

import pandas as pd

from phase16.indicators import is_in_session
from phase16.resample import cme_session_date

from .config import MIN_BARS_BETWEEN_SAME_DIR, ONE_ACTIVE_TRADE, RTH_SESSION


def filter_rth_signals(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    mask = [is_in_session(ts, RTH_SESSION) for ts in signals["entry_timestamp"]]
    return signals.loc[mask].copy()


def _bar_index(market: pd.DataFrame, ts: pd.Timestamp) -> Optional[int]:
    loc = market.index.get_indexer([ts], method="pad")
    if loc.size == 0 or loc[0] < 0:
        return None
    return int(loc[0])


def dedupe_signals(
    signals: pd.DataFrame,
    market: pd.DataFrame,
    *,
    min_bars_same_dir: int = MIN_BARS_BETWEEN_SAME_DIR,
    one_active: bool = ONE_ACTIVE_TRADE,
    max_hold_bars: int = 4,
    event_col: str = "event_id",
    max_per_rth_day: int = 2,
) -> pd.DataFrame:
    """Causal dedupe: one active trade, min bars between same direction, one per event, daily cap."""
    if signals.empty:
        return signals.copy()
    sig = signals.sort_values("entry_timestamp").copy()
    if event_col in sig.columns:
        sig = sig.drop_duplicates(subset=[event_col], keep="first")
    kept = []
    active_until_bar = -1
    last_dir_bar: dict[str, int] = {"Long": -999, "Short": -999}
    seen_events: set[str] = set()
    day_counts: dict[object, int] = {}
    for _, row in sig.iterrows():
        ts = row["entry_timestamp"]
        bar = _bar_index(market, ts)
        if bar is None:
            continue
        direction = str(row["direction"])
        eid = str(row.get(event_col, f"{direction}_{ts}"))
        if eid in seen_events:
            continue
        rth_day = cme_session_date(pd.DatetimeIndex([ts]))[0]
        if day_counts.get(rth_day, 0) >= max_per_rth_day:
            continue
        if one_active and bar <= active_until_bar:
            continue
        if bar - last_dir_bar.get(direction, -999) < min_bars_same_dir:
            continue
        kept.append(row)
        seen_events.add(eid)
        last_dir_bar[direction] = bar
        day_counts[rth_day] = day_counts.get(rth_day, 0) + 1
        if one_active:
            active_until_bar = bar + max_hold_bars
    return pd.DataFrame(kept).reset_index(drop=True)


def rth_trading_dates(market: pd.DataFrame) -> pd.Index:
    idx = market.index
    dates = []
    for ts in idx:
        if is_in_session(ts, RTH_SESSION):
            dates.append(cme_session_date(pd.DatetimeIndex([ts]))[0])
    return pd.Index(sorted(set(dates)))
