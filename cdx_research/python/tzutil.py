"""Timezone-aware conversion for CDX alignment. No manual hour offsets."""
from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")

WIN_TZ_TO_IANA = {
    "eastern standard time": "America/New_York",
    "eastern daylight time": "America/New_York",
    "central standard time": "America/Chicago",
    "central daylight time": "America/Chicago",
    "utc": "UTC",
    "gmt": "UTC",
    "america/new_york": "America/New_York",
    "america/chicago": "America/Chicago",
}


def iana_from_chart_tz(name: str | None) -> str:
    if not name:
        return "America/New_York"
    key = str(name).strip().lower()
    if key in WIN_TZ_TO_IANA:
        return WIN_TZ_TO_IANA[key]
    return str(name).strip()


def to_utc(series: pd.Series, source_tz: str) -> pd.DatetimeIndex:
    parsed = pd.to_datetime(series, utc=False, errors="coerce")
    idx = pd.DatetimeIndex(parsed)
    if idx.tz is None:
        idx = idx.tz_localize(source_tz, ambiguous="infer", nonexistent="shift_forward")
    return idx.tz_convert("UTC")


def to_et(utc_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return utc_index.tz_convert(ET)


def minute_floor_et(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        ts = ts.tz_localize(ET)
    else:
        ts = ts.tz_convert(ET)
    return ts.replace(second=0, microsecond=0)
