"""Webhook signal contract — Pine is signal authority."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import hashlib
import json
import uuid


SCHEMA_VERSION = "1.0"
SIGNAL_EVENTS = frozenset({"SIGNAL_LONG", "SIGNAL_SHORT"})
OPTIONAL_EVENTS = frozenset({"EXIT_STOP", "EXIT_TARGET", "ENTER_LONG", "ENTER_SHORT"})


class WebhookReason(str, Enum):
    WEBHOOK_VALID = "WEBHOOK_VALID"
    WEBHOOK_INVALID = "WEBHOOK_INVALID"
    SIGNAL_DUPLICATE = "SIGNAL_DUPLICATE"
    SIGNAL_STALE = "SIGNAL_STALE"
    SIGNAL_WRONG_SYMBOL = "SIGNAL_WRONG_SYMBOL"
    SIGNAL_WRONG_TIMEFRAME = "SIGNAL_WRONG_TIMEFRAME"
    SIGNAL_HASH_MISMATCH = "SIGNAL_HASH_MISMATCH"


@dataclass
class PineSignal:
    schema_version: str
    strategy: str
    pine_hash: str
    signal_id: str
    event: str
    symbol: str
    timeframe: str
    signal_time_utc: datetime
    signal_bar_time_utc: datetime
    signal_price: float
    atr: float
    evidence: int
    context: str
    state: str
    received_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def direction(self) -> str:
        if self.event == "SIGNAL_LONG":
            return "LONG"
        if self.event == "SIGNAL_SHORT":
            return "SHORT"
        return ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy": self.strategy,
            "pine_hash": self.pine_hash,
            "signal_id": self.signal_id,
            "event": self.event,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "signal_time_utc": self.signal_time_utc.isoformat(),
            "signal_bar_time_utc": self.signal_bar_time_utc.isoformat(),
            "signal_price": self.signal_price,
            "atr": self.atr,
            "evidence": self.evidence,
            "context": self.context,
            "state": self.state,
            "received_at_utc": self.received_at_utc.isoformat(),
        }


def _parse_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_signal_payload(payload: dict[str, Any], received_at: datetime | None = None) -> PineSignal:
    return PineSignal(
        schema_version=str(payload["schema_version"]),
        strategy=str(payload["strategy"]),
        pine_hash=str(payload["pine_hash"]),
        signal_id=str(payload["signal_id"]),
        event=str(payload["event"]),
        symbol=str(payload["symbol"]),
        timeframe=str(payload["timeframe"]),
        signal_time_utc=_parse_ts(str(payload["signal_time_utc"])),
        signal_bar_time_utc=_parse_ts(str(payload["signal_bar_time_utc"])),
        signal_price=float(payload["signal_price"]),
        atr=float(payload["atr"]),
        evidence=int(payload["evidence"]),
        context=str(payload.get("context", "")),
        state=str(payload.get("state", "")),
        received_at_utc=received_at or datetime.now(timezone.utc),
        raw=dict(payload),
    )


def make_test_signal(
    event: str = "SIGNAL_LONG",
    *,
    signal_id: str | None = None,
    symbol: str = "NQ",
    pine_hash: str = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f",
    signal_time_utc: datetime | None = None,
    signal_bar_time_utc: datetime | None = None,
    signal_price: float = 20000.0,
    atr: float = 10.0,
    evidence: int = 5,
    context: str = "BULLISH",
    state: str = "IN_LONG",
) -> PineSignal:
    now = datetime.now(timezone.utc)
    bar = signal_bar_time_utc or now
    sig_t = signal_time_utc or now
    sid = signal_id or str(uuid.uuid4())
    return PineSignal(
        schema_version=SCHEMA_VERSION,
        strategy="Phase72A",
        pine_hash=pine_hash,
        signal_id=sid,
        event=event,
        symbol=symbol,
        timeframe="1m",
        signal_time_utc=sig_t,
        signal_bar_time_utc=bar,
        signal_price=signal_price,
        atr=atr,
        evidence=evidence,
        context=context,
        state=state,
        received_at_utc=now,
    )


def payload_fingerprint(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
