"""JSON-lines codec with fail-closed validation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from phase85.protocol.messages import (
    ALLOWED_COMMANDS,
    ALLOWED_EVENTS,
    PROTOCOL_VERSION,
    Command,
    Event,
)


class ProtocolError(ValueError):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def parse_utc(ts: str) -> datetime:
    if not ts or not isinstance(ts, str):
        raise ProtocolError("INVALID_TIMESTAMP", "missing timestamp")
    raw = ts
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ProtocolError("INVALID_TIMESTAMP", str(exc)) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def encode_message(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=False) + "\n"


def decode_line(line: str) -> dict[str, Any]:
    text = line.strip()
    if not text:
        raise ProtocolError("MALFORMED_JSON", "empty line")
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError("MALFORMED_JSON", str(exc)) from exc
    if not isinstance(obj, dict):
        raise ProtocolError("MALFORMED_JSON", "message must be object")
    return obj


def command_from_dict(obj: dict[str, Any]) -> Command:
    version = obj.get("protocol_version", PROTOCOL_VERSION)
    try:
        version_i = int(version)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("UNSUPPORTED_PROTOCOL", str(version)) from exc
    if version_i != PROTOCOL_VERSION:
        raise ProtocolError("UNSUPPORTED_PROTOCOL", str(version_i))

    name = str(obj.get("command", ""))
    if name not in ALLOWED_COMMANDS:
        raise ProtocolError("UNKNOWN_COMMAND", name or "missing")

    command_id = str(obj.get("command_id", "")).strip()
    if not command_id:
        raise ProtocolError("MALFORMED_JSON", "command_id required")

    created = str(obj.get("created_at_utc", "")).strip()
    if created:
        parse_utc(created)

    qty = obj.get("quantity", 1)
    try:
        quantity = int(qty)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("INVALID_QUANTITY", str(qty)) from exc
    if quantity < 1:
        raise ProtocolError("INVALID_QUANTITY", str(quantity))

    extra = {
        k: v
        for k, v in obj.items()
        if k
        not in {
            "protocol_version",
            "command",
            "command_id",
            "event_id",
            "signal_id",
            "created_at_utc",
            "account",
            "instrument",
            "side",
            "quantity",
            "order_type",
            "limit_price",
            "stop_price",
            "target_price",
            "time_in_force",
        }
    }
    return Command(
        command=name,
        command_id=command_id,
        event_id=str(obj.get("event_id", "")),
        signal_id=str(obj.get("signal_id", "")),
        created_at_utc=created,
        account=str(obj.get("account", "")),
        instrument=str(obj.get("instrument", "")),
        side=str(obj.get("side", "")),
        quantity=quantity,
        order_type=str(obj.get("order_type", "MARKET")),
        limit_price=_opt_float(obj.get("limit_price")),
        stop_price=_opt_float(obj.get("stop_price")),
        target_price=_opt_float(obj.get("target_price")),
        time_in_force=str(obj.get("time_in_force", "DAY")),
        protocol_version=version_i,
        extra=extra,
    )


def event_from_dict(obj: dict[str, Any]) -> Event:
    name = str(obj.get("event", obj.get("type", "")))
    if name not in ALLOWED_EVENTS:
        raise ProtocolError("UNKNOWN_EVENT", name or "missing")
    extra = {
        k: v
        for k, v in obj.items()
        if k
        not in {
            "protocol_version",
            "event",
            "type",
            "command_id",
            "event_id",
            "signal_id",
            "created_at_utc",
            "reason",
            "order_id",
            "fill_price",
            "fill_quantity",
            "remaining_quantity",
            "account",
            "instrument",
            "side",
            "quantity",
            "existing_order_state",
        }
    }
    return Event(
        event=name,
        command_id=str(obj.get("command_id", "")),
        event_id=str(obj.get("event_id", "")),
        signal_id=str(obj.get("signal_id", "")),
        created_at_utc=str(obj.get("created_at_utc", "")),
        reason=str(obj.get("reason", "")),
        order_id=str(obj.get("order_id", "")),
        fill_price=_opt_float(obj.get("fill_price")),
        fill_quantity=_opt_int(obj.get("fill_quantity")),
        remaining_quantity=_opt_int(obj.get("remaining_quantity")),
        account=str(obj.get("account", "")),
        instrument=str(obj.get("instrument", "")),
        side=str(obj.get("side", "")),
        quantity=_opt_int(obj.get("quantity")),
        existing_order_state=str(obj.get("existing_order_state", "")),
        protocol_version=int(obj.get("protocol_version", PROTOCOL_VERSION)),
        extra=extra,
    )


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
