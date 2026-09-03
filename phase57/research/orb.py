"""Opening Range / ORB detection and event classification.

ORB windows (CT): ORB5 (08:30-08:35), ORB15 (08:30-08:45), ORB30 (08:30-09:00).
Range not actionable until its window fully closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time as dtime

import numpy as np
import pandas as pd


@dataclass
class ORBRange:
    date: object
    window_min: int       # 5, 15, or 30
    or_high: float
    or_low: float
    or_mid: float
    or_width: float
    width_atr: float
    actionable_i: int     # first bar AFTER range closes
    actionable_ts: pd.Timestamp
    first_high_break_i: int | None = None
    first_low_break_i: int | None = None
    first_break_dir: str | None = None


@dataclass
class ORBEvent:
    orb: ORBRange
    event_type: str       # O1-O10
    timestamp_ct: pd.Timestamp
    entry_i: int
    direction: str        # "LONG" or "SHORT"
    description: str = ""


CASH_OPEN = dtime(8, 30)


def _orb_end(window_min: int) -> dtime:
    total = 8 * 60 + 30 + window_min
    return dtime(total // 60, total % 60)


def detect_orb_ranges(
    m1: pd.DataFrame,
    window_min: int = 5,
) -> list[ORBRange]:
    """Detect opening ranges from closed 1M bars. CT timezone required."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    orb_end = _orb_end(window_min)
    ranges: list[ORBRange] = []
    seen_dates: set = set()

    for i in range(n):
        ts = idx[i]
        t = ts.time()
        d = ts.date()
        if d in seen_dates:
            continue
        if t < CASH_OPEN or t >= orb_end:
            continue
        # Collect all bars in [08:30, orb_end)
        or_bars = []
        j = i
        while j < n and idx[j].date() == d and idx[j].time() < orb_end:
            or_bars.append(j)
            j += 1
        if not or_bars:
            continue
        seen_dates.add(d)
        or_hi = float(max(hi[b] for b in or_bars))
        or_lo = float(min(lo[b] for b in or_bars))
        or_mid = (or_hi + or_lo) / 2
        or_width = or_hi - or_lo
        # actionable = first bar whose time >= orb_end on same date
        act_i = None
        for k in range(or_bars[-1] + 1, min(n, or_bars[-1] + 500)):
            if idx[k].date() != d:
                break
            if idx[k].time() >= orb_end:
                act_i = k
                break
        if act_i is None:
            continue
        a = float(atr_arr[act_i]) if np.isfinite(atr_arr[act_i]) else 1.0
        ranges.append(ORBRange(
            date=d,
            window_min=window_min,
            or_high=or_hi,
            or_low=or_lo,
            or_mid=or_mid,
            or_width=or_width,
            width_atr=or_width / a,
            actionable_i=act_i,
            actionable_ts=idx[act_i],
        ))
    return ranges


def classify_orb_events(
    orb: ORBRange,
    m1: pd.DataFrame,
    *,
    max_bars: int = 390,
) -> list[ORBEvent]:
    """Classify ORB interaction events (O1-O10) after range becomes actionable."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    idx = m1.index
    n = len(m1)
    events: list[ORBEvent] = []
    end = min(n, orb.actionable_i + max_bars)
    high_broken = False
    low_broken = False
    high_break_i = None
    low_break_i = None
    returned_after_high = False
    returned_after_low = False

    for j in range(orb.actionable_i, end):
        if idx[j].date() != orb.date:
            break
        c = cl[j]
        # O1/O2: direct breakout
        if not high_broken and c > orb.or_high:
            high_broken = True
            high_break_i = j
            orb.first_high_break_i = j
            if orb.first_break_dir is None:
                orb.first_break_dir = "LONG"
            events.append(ORBEvent(orb, "O1", idx[j], j, "LONG", "direct high breakout"))
        if not low_broken and c < orb.or_low:
            low_broken = True
            low_break_i = j
            orb.first_low_break_i = j
            if orb.first_break_dir is None:
                orb.first_break_dir = "SHORT"
            events.append(ORBEvent(orb, "O2", idx[j], j, "SHORT", "direct low breakout"))
        # O3/O4: breakout + retest (price returns to range edge)
        if high_broken and not returned_after_high and lo[j] <= orb.or_high and c > orb.or_high:
            returned_after_high = True
            events.append(ORBEvent(orb, "O3", idx[j], j, "LONG", "high breakout retest"))
        if low_broken and not returned_after_low and hi[j] >= orb.or_low and c < orb.or_low:
            returned_after_low = True
            events.append(ORBEvent(orb, "O4", idx[j], j, "SHORT", "low breakout retest"))
        # O5/O6: sweep + failure (breaks beyond then closes back inside)
        if high_broken and not returned_after_high and hi[j] > orb.or_high and c < orb.or_high and c > orb.or_low:
            events.append(ORBEvent(orb, "O5", idx[j], j, "SHORT", "high sweep failure"))
        if low_broken and not returned_after_low and lo[j] < orb.or_low and c > orb.or_low and c < orb.or_high:
            events.append(ORBEvent(orb, "O6", idx[j], j, "LONG", "low sweep failure"))
    return events


def detect_all_orb_events(
    m1: pd.DataFrame,
    windows: tuple[int, ...] = (5, 15, 30),
) -> pd.DataFrame:
    """Detect ORB ranges and classify events for all windows."""
    rows: list[dict] = []
    for w in windows:
        ranges = detect_orb_ranges(m1, window_min=w)
        for orb in ranges:
            events = classify_orb_events(orb, m1)
            for ev in events:
                rows.append({
                    "date": orb.date,
                    "window_min": w,
                    "or_high": orb.or_high,
                    "or_low": orb.or_low,
                    "or_width": orb.or_width,
                    "width_atr": orb.width_atr,
                    "event_type": ev.event_type,
                    "timestamp_ct": ev.timestamp_ct,
                    "entry_i": ev.entry_i,
                    "direction": ev.direction,
                    "description": ev.description,
                    "first_break_dir": orb.first_break_dir,
                })
    return pd.DataFrame(rows) if rows else pd.DataFrame()
