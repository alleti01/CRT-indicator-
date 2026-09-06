"""Silver Bullet windows and session context — America/New_York."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterator

import pandas as pd

from .config import OVERNIGHT_START, RTH_CLOSE, RTH_OPEN, SB_WINDOWS, TIMEZONE


def _t(h: int, m: int) -> time:
    return time(h, m)


RTH_OPEN_T = _t(*RTH_OPEN)
RTH_CLOSE_T = _t(*RTH_CLOSE)
OVERNIGHT_START_T = _t(*OVERNIGHT_START)


def is_rth(ts_et: pd.Timestamp) -> bool:
    return RTH_OPEN_T <= ts_et.time() < RTH_CLOSE_T


def window_bounds(calendar_date: date, window_id: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    (sh, sm), (eh, em) = SB_WINDOWS[window_id]
    start = pd.Timestamp(datetime.combine(calendar_date, time(sh, sm)), tz=TIMEZONE)
    end = pd.Timestamp(datetime.combine(calendar_date, time(eh, em)), tz=TIMEZONE)
    return start, end


def iter_window_instances(index: pd.DatetimeIndex) -> Iterator[tuple[date, str, pd.Timestamp, pd.Timestamp]]:
    """Yield (calendar_date, window_id, start_utc, end_utc) for days with data."""
    ts_et = index.tz_convert(TIMEZONE) if index.tz else index.tz_localize(TIMEZONE_UTC).tz_convert(TIMEZONE)
    dates = sorted(set(ts_et.date))
    for d in dates:
        if d.weekday() >= 5:
            continue
        for wid in SB_WINDOWS:
            ws, we = window_bounds(d, wid)
            ws_utc = ws.tz_convert("UTC")
            we_utc = we.tz_convert("UTC")
            if (index >= ws_utc).any() and (index <= we_utc).any():
                yield d, wid, ws_utc, we_utc


from .config import TIMEZONE_UTC  # noqa: E402
