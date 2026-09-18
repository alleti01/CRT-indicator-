"""Small command / event vocabulary. No generic broker passthrough."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = 1

ALLOWED_COMMANDS = frozenset(
    {
        "ENTER_LONG",
        "ENTER_SHORT",
        "PLACE_PROTECTION",
        "CANCEL_ENTRY",
        "FLATTEN",
        "QUERY_POSITION",
        "QUERY_ORDERS",
        "PING",
        "RECONCILE",
    }
)

ALLOWED_EVENTS = frozenset(
    {
        "EXECUTION_BRIDGE_READY",
        "ACCOUNT_STATE",
        "CONNECTION_STATE",
        "ORDER_RECEIVED",
        "ORDER_SUBMITTED",
        "ORDER_ACCEPTED",
        "ORDER_REJECTED",
        "ORDER_CANCELLED",
        "PARTIAL_FILL",
        "FILLED",
        "STOP_WORKING",
        "TARGET_WORKING",
        "STOP_FILLED",
        "TARGET_FILLED",
        "POSITION_UPDATE",
        "POSITION_FLAT",
        "RECONCILIATION_RESULT",
        "PROTECTION_FAILURE",
        "DUPLICATE_COMMAND",
        "PONG",
        "COMMAND_REJECTED",
    }
)

REJECT_REASONS = frozenset(
    {
        "AUTH_FAILED",
        "NOT_AUTHENTICATED",
        "UNKNOWN_COMMAND",
        "UNSUPPORTED_PROTOCOL",
        "MALFORMED_JSON",
        "INVALID_TIMESTAMP",
        "INVALID_QUANTITY",
        "REJECT_MAX_QUANTITY",
        "REJECT_ACCOUNT_NOT_ALLOWED",
        "REJECT_CONTRACT_MISMATCH",
        "EXECUTION_NOT_READY",
        "DUPLICATE_COMMAND",
        "REJECT_NO_AUTO_REVERSE",
        "REJECT_POSITION_OPEN",
        "MARKET_CLOSED",
        "BROKER_REJECT",
        "ROUTING_UNAVAILABLE",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Command:
    command: str
    command_id: str
    event_id: str = ""
    signal_id: str = ""
    created_at_utc: str = ""
    account: str = ""
    instrument: str = ""
    side: str = ""
    quantity: int = 1
    order_type: str = "MARKET"
    limit_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    time_in_force: str = "DAY"
    protocol_version: int = PROTOCOL_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "command": self.command,
            "command_id": self.command_id,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "created_at_utc": self.created_at_utc,
            "account": self.account,
            "instrument": self.instrument,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
        }
        if self.limit_price is not None:
            payload["limit_price"] = self.limit_price
        if self.stop_price is not None:
            payload["stop_price"] = self.stop_price
        if self.target_price is not None:
            payload["target_price"] = self.target_price
        payload.update(self.extra)
        return payload


@dataclass
class Event:
    event: str
    command_id: str = ""
    event_id: str = ""
    signal_id: str = ""
    created_at_utc: str = ""
    reason: str = ""
    order_id: str = ""
    fill_price: float | None = None
    fill_quantity: int | None = None
    remaining_quantity: int | None = None
    account: str = ""
    instrument: str = ""
    side: str = ""
    quantity: int | None = None
    existing_order_state: str = ""
    protocol_version: int = PROTOCOL_VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol_version": self.protocol_version,
            "event": self.event,
            "command_id": self.command_id,
            "event_id": self.event_id,
            "signal_id": self.signal_id,
            "created_at_utc": self.created_at_utc,
            "reason": self.reason,
            "order_id": self.order_id,
            "account": self.account,
            "instrument": self.instrument,
            "side": self.side,
            "existing_order_state": self.existing_order_state,
        }
        if self.fill_price is not None:
            payload["fill_price"] = self.fill_price
        if self.fill_quantity is not None:
            payload["fill_quantity"] = self.fill_quantity
        if self.remaining_quantity is not None:
            payload["remaining_quantity"] = self.remaining_quantity
        if self.quantity is not None:
            payload["quantity"] = self.quantity
        payload.update(self.extra)
        return payload
