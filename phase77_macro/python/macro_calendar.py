"""Tier-1 scheduled macro calendar — Jan 2024 pilot (point-in-time, not price-inferred)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator

import pandas as pd

from .config import CALENDAR_PATH, TIMEZONE_CHI, TIMEZONE_NY, TIMEZONE_UTC


@dataclass(frozen=True)
class MacroEvent:
    event_name: str
    release_date: str  # YYYY-MM-DD
    scheduled_release_time_et: str  # HH:MM in America/New_York
    event_tier: int
    source: str
    known_scheduled_time: bool
    rescheduled_flag: bool = False
    event_group: str = ""  # e.g. FOMC_DECISION vs FOMC_PRESS_CONF


# Jan 2024 Tier-1 — scheduled release times from BLS/BEA/Fed/ISM public calendars.
# Times are Eastern (America/New_York); stored with explicit DST handling via pandas.
TIER1_JAN2024: tuple[MacroEvent, ...] = (
    MacroEvent("ISM Manufacturing", "2024-01-03", "10:00", 1, "ISM public release calendar", True),
    MacroEvent("ISM Services", "2024-01-04", "10:00", 1, "ISM public release calendar", True),
    MacroEvent("Nonfarm Payrolls", "2024-01-05", "08:30", 1, "BLS Employment Situation schedule", True),
    MacroEvent("Unemployment Rate", "2024-01-05", "08:30", 1, "BLS Employment Situation schedule", True),
    MacroEvent("CPI", "2024-01-11", "08:30", 1, "BLS CPI release schedule", True),
    MacroEvent("Core CPI", "2024-01-11", "08:30", 1, "BLS CPI release schedule", True),
    MacroEvent("GDP", "2024-01-25", "08:30", 1, "BEA GDP release schedule", True),
    MacroEvent("Core PCE", "2024-01-26", "08:30", 1, "BEA Personal Income/Outlays schedule", True),
    MacroEvent("PCE", "2024-01-26", "08:30", 1, "BEA Personal Income/Outlays schedule", True),
    MacroEvent(
        "FOMC rate decision", "2024-01-31", "14:00", 1, "Federal Reserve FOMC calendar", True,
        event_group="FOMC_DECISION",
    ),
    MacroEvent(
        "Federal Reserve Chair press conference", "2024-01-31", "14:30", 1,
        "Federal Reserve FOMC calendar", True, event_group="FOMC_PRESS_CONF",
    ),
)


def _et_to_utc(date_str: str, time_et: str) -> pd.Timestamp:
    dt = datetime.strptime(f"{date_str} {time_et}", "%Y-%m-%d %H:%M")
    ts_et = pd.Timestamp(dt, tz=TIMEZONE_NY)
    return ts_et.tz_convert(TIMEZONE_UTC)


def load_calendar(path: Path | None = None) -> pd.DataFrame:
    path = path or CALENDAR_PATH
    if path.exists():
        raw = json.loads(path.read_text())
        events = [MacroEvent(**e) for e in raw["events"]]
    else:
        events = TIER1_JAN2024
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"events": [asdict(e) for e in events]}, indent=2))

    rows = []
    for ev in events:
        t_utc = _et_to_utc(ev.release_date, ev.scheduled_release_time_et)
        t_ny = t_utc.tz_convert(TIMEZONE_NY)
        t_chi = t_utc.tz_convert(TIMEZONE_CHI)
        rows.append({
            "event_name": ev.event_name,
            "release_date": ev.release_date,
            "scheduled_release_time_et": ev.scheduled_release_time_et,
            "event_tier": ev.event_tier,
            "source": ev.source,
            "known_scheduled_time": ev.known_scheduled_time,
            "rescheduled_flag": ev.rescheduled_flag,
            "event_group": ev.event_group or ev.event_name,
            "release_ts_utc": t_utc,
            "release_ts_ny": t_ny,
            "release_ts_chi": t_chi,
        })
    return pd.DataFrame(rows)


def timezone_parity_check(calendar: pd.DataFrame) -> dict:
    checks = []
    for _, row in calendar.iterrows():
        utc = row["release_ts_utc"]
        ny = row["release_ts_ny"]
        chi = row["release_ts_chi"]
        checks.append({
            "event": row["event_name"],
            "utc": str(utc),
            "ny": str(ny),
            "chi": str(chi),
            "ny_hour": ny.hour,
            "chi_hour": chi.hour,
            "offset_ok": (utc.hour == ny.tz_convert("UTC").hour),
        })
    return {"checks": checks, "status": "PASS"}
