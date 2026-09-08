"""JSON-line protocol for NinjaTrader → Python bar feed."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from phase73.market_data.bar import Bar


def parse_line(line: str) -> dict[str, Any]:
    line = line.strip().lstrip("\ufeff")
    if not line:
        raise ValueError("empty line")
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError("message must be object")
    return obj


def parse_utc(ts: str) -> datetime:
    """Parse ISO-8601 UTC timestamp (Z or +00:00)."""
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bar_from_message(msg: dict[str, Any]) -> Bar:
    if msg.get("type") != "bar":
        raise ValueError(f"not a bar message: {msg.get('type')}")
    ts = parse_utc(str(msg["ts_utc"]))
    ts = ts.replace(second=0, microsecond=0)
    return Bar(
        timestamp=ts,
        open=float(msg["open"]),
        high=float(msg["high"]),
        low=float(msg["low"]),
        close=float(msg["close"]),
        volume=float(msg.get("volume", 0)),
    )


@dataclass(frozen=True)
class HelloMessage:
    contract: str
    instrument: str
    auth: str
    seq: int
    chart_timezone: str = "UTC"


def hello_from_message(msg: dict[str, Any]) -> HelloMessage:
    if msg.get("type") != "hello":
        raise ValueError(f"not a hello message: {msg.get('type')}")
    return HelloMessage(
        contract=str(msg.get("contract", "")),
        instrument=str(msg.get("instrument", "")),
        auth=str(msg.get("auth", "")),
        seq=int(msg.get("seq", 0)),
        chart_timezone=str(msg.get("chart_timezone", "UTC")),
    )


def encode_ack(*, ok: bool, detail: str = "", seq: int = 0) -> str:
    return json.dumps({"type": "ack", "ok": ok, "detail": detail, "seq": seq}, separators=(",", ":")) + "\n"
