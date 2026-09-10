"""Load Phase72A fired-signal logs and index by bar time (UTC only)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from signal_ledger.config import NULLABLE_GATE_NAMES


@dataclass
class FiredSignal:
    event_id: str
    bar_time: pd.Timestamp
    direction: str  # "long" | "short"
    event: str
    gate_state: dict[str, bool | None] | None = None


def _parse_gate_state(gs: dict) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {}
    for k, v in gs.items():
        if k in NULLABLE_GATE_NAMES and v is None:
            out[k] = None
        else:
            out[k] = bool(v)
    return out


def _parse_utc_ms(v) -> pd.Timestamp:
    if isinstance(v, (int, float)):
        return pd.to_datetime(v, unit="ms", utc=True)
    s = str(v)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return pd.to_datetime(s, utc=True)


def _parse_ts(v) -> pd.Timestamp:
    """Parse timestamp field — must resolve to UTC."""
    if isinstance(v, (int, float)):
        unit = "ms" if v > 1e12 else "s"
        return pd.to_datetime(v, unit=unit, utc=True)
    s = str(v)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    ts = pd.to_datetime(s, utc=True)
    if ts.tz is None:
        raise ValueError(f"Timestamp must be timezone-aware UTC: {v}")
    return ts


def load_signal_log(paths: list[Path]) -> dict[pd.Timestamp, FiredSignal]:
    """
    Load SIGNAL_LONG / SIGNAL_SHORT events from jsonl logs.
    Keys are signal_bar_time (UTC), floored to 1-minute for bar matching.

    Supports schema 1.2 gate_state in alert payload (Layer D).
    """
    out: dict[pd.Timestamp, FiredSignal] = {}
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = obj.get("payload", obj)
            event = payload.get("event", "")
            if event not in ("SIGNAL_LONG", "SIGNAL_SHORT"):
                continue

            bar_ts = (
                payload.get("signal_bar_time_utc_ms")
                or payload.get("signal_bar_time_utc")
                or payload.get("signal_time_utc")
                or payload.get("signal_time")
            )
            if bar_ts is None:
                continue
            if isinstance(bar_ts, (int, float)) or str(bar_ts).isdigit():
                ts = _parse_utc_ms(bar_ts)
            else:
                ts = _parse_ts(bar_ts)
            ts = ts.floor("min")

            direction = "long" if "LONG" in event else "short"
            eid = str(payload.get("event_id") or payload.get("signal_id") or obj.get("event_id") or "")

            gs = payload.get("gate_state")
            if isinstance(gs, str):
                gs = json.loads(gs)
            gate_state = _parse_gate_state(gs) if isinstance(gs, dict) else None

            out[ts] = FiredSignal(
                event_id=eid, bar_time=ts, direction=direction, event=event, gate_state=gate_state
            )
    return out
