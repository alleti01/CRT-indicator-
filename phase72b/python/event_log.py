"""Event log schema and timezone formatting for Phase72B parity."""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from phase72b.python.autonomous_mirror_engine import EventRow


def _tz_cols(ts: pd.Timestamp) -> dict[str, str]:
    if ts.tzinfo is None:
        ts = ts.tz_localize("America/Chicago")
    return {
        "timestamp_utc": ts.tz_convert("UTC").isoformat(),
        "timestamp_chicago": ts.tz_convert("America/Chicago").isoformat(),
        "timestamp_ny": ts.tz_convert("America/New_York").isoformat(),
    }


def events_to_dataframe(events: list[EventRow]) -> pd.DataFrame:
    rows = []
    for e in events:
        base = asdict(e)
        ts = e.timestamp
        base.pop("timestamp")
        rows.append({"timestamp": ts, **_tz_cols(ts), **base})
    return pd.DataFrame(rows)


def write_event_log(events: list[EventRow], path: str) -> None:
    df = events_to_dataframe(events)
    df.to_csv(path, index=False)
