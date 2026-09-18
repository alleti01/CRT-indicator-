"""Deterministic fake CRTExecutionBridge for unit tests (no NinjaTrader)."""
from __future__ import annotations

import hmac
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from phase85.protocol.codec import ProtocolError, command_from_dict, decode_line, event_from_dict
from phase85.protocol.messages import ALLOWED_COMMANDS, Command, Event, utc_now


def _iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class FakePosition:
    side: str = "FLAT"
    quantity: int = 0
    instrument: str = "MNQ 12-26"
    average_price: float = 0.0


@dataclass
class FakeOrder:
    order_id: str
    kind: str
    side: str
    quantity: int
    state: str = "WORKING"
    price: float | None = None


@dataclass
class FakeExecutionBridge:
    expected_token: str
    expected_account: str = "SIM101"
    expected_instrument: str = "MNQ 12-26"
    allowed_root: str = "MNQ"
    max_quantity: int = 1
    connected: bool = False
    authenticated: bool = False
    account_verified: bool = False
    contract_verified: bool = False
    account: str = ""
    instrument: str = "MNQ 12-26"
    fill_price: float = 20000.0
    scenario: str = "fill_then_protect"
    position: FakePosition = field(default_factory=FakePosition)
    orders: dict[str, FakeOrder] = field(default_factory=dict)
    command_ids: dict[str, str] = field(default_factory=dict)
    submitted_commands: list[Command] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    protection_should_fail: bool = False
    reject_next_entry: bool = False
    partial_then_fill: bool = False
    disconnected_after_protect: bool = False
    out_of_order_events: bool = False

    def connect(self, token: str) -> bool:
        if not hmac.compare_digest(token or "", self.expected_token or ""):
            self.connected = False
            self.authenticated = False
            return False
        self.connected = True
        self.authenticated = True
        self.account = self.expected_account
        self.instrument = self.expected_instrument
        self.account_verified = True
        self.contract_verified = True
        return True

    def disconnect(self) -> None:
        self.connected = False
        self.authenticated = False

    def snapshot(self) -> dict:
        return {
            "side": self.position.side,
            "quantity": self.position.quantity,
            "instrument": self.position.instrument,
            "working_stop": any(o.kind == "STOP" and o.state == "WORKING" for o in self.orders.values()),
            "working_target": any(o.kind == "TARGET" and o.state == "WORKING" for o in self.orders.values()),
            "unexpected_orders": 0,
            "orphan_orders": sum(1 for o in self.orders.values() if o.kind == "ORPHAN"),
            "connected": self.connected and self.authenticated,
            "working_orders": len([o for o in self.orders.values() if o.state == "WORKING"]),
        }

    def handle_line(self, line: str, token: str) -> list[Event]:
        if not hmac.compare_digest(token or "", self.expected_token or ""):
            return [self._event("COMMAND_REJECTED", reason="AUTH_FAILED")]
        try:
            obj = decode_line(line)
            cmd = command_from_dict(obj)
        except ProtocolError as exc:
            return [self._event("COMMAND_REJECTED", reason=exc.reason)]
        return self.send(cmd)

    def send(self, command: Command) -> list[Event]:
        if not self.connected or not self.authenticated:
            return [self._event("COMMAND_REJECTED", reason="ROUTING_UNAVAILABLE", command=command)]
        if command.command not in ALLOWED_COMMANDS:
            return [self._event("COMMAND_REJECTED", reason="UNKNOWN_COMMAND", command=command)]

        if command.command_id in self.command_ids:
            return [
                self._event(
                    "DUPLICATE_COMMAND",
                    command=command,
                    reason="DUPLICATE_COMMAND",
                    existing=self.command_ids[command.command_id],
                )
            ]

        if command.account and command.account != self.expected_account:
            return [self._event("COMMAND_REJECTED", reason="REJECT_ACCOUNT_NOT_ALLOWED", command=command)]

        root = (command.instrument or self.instrument).upper().split()[0]
        if command.command in {"ENTER_LONG", "ENTER_SHORT", "PLACE_PROTECTION"}:
            if root != self.allowed_root.upper():
                return [self._event("COMMAND_REJECTED", reason="REJECT_CONTRACT_MISMATCH", command=command)]
            if command.quantity > self.max_quantity:
                return [self._event("COMMAND_REJECTED", reason="REJECT_MAX_QUANTITY", command=command)]

        self.submitted_commands.append(command)
        if command.command in {"ENTER_LONG", "ENTER_SHORT", "PLACE_PROTECTION", "FLATTEN", "CANCEL_ENTRY"}:
            self.command_ids[command.command_id] = "RECEIVED"

        if command.command == "PING":
            return [self._event("PONG", command=command)]
        if command.command == "QUERY_POSITION":
            return [self._position_event(command)]
        if command.command == "QUERY_ORDERS":
            return [
                self._event(
                    "RECONCILIATION_RESULT",
                    command=command,
                    extra={"working_orders": len(self.orders), "orders": [o.kind for o in self.orders.values()]},
                )
            ]
        if command.command == "RECONCILE":
            snap = self.snapshot()
            return [self._event("RECONCILIATION_RESULT", command=command, extra=snap)]
        if command.command == "CANCEL_ENTRY":
            for order in self.orders.values():
                if order.kind == "ENTRY" and order.state in {"WORKING", "ACCEPTED", "SUBMITTED"}:
                    order.state = "CANCELLED"
            return [self._event("ORDER_CANCELLED", command=command)]
        if command.command == "FLATTEN":
            return self._flatten(command)
        if command.command == "PLACE_PROTECTION":
            return self._protect(command)
        if command.command in {"ENTER_LONG", "ENTER_SHORT"}:
            return self._enter(command)
        return [self._event("COMMAND_REJECTED", reason="UNKNOWN_COMMAND", command=command)]

    def fill_target(self, command: Command | None = None) -> list[Event]:
        cmd = command or (self.submitted_commands[-1] if self.submitted_commands else Command("FLATTEN", "x"))
        target = next((o for o in self.orders.values() if o.kind == "TARGET"), None)
        stop = next((o for o in self.orders.values() if o.kind == "STOP"), None)
        events = [self._event("TARGET_FILLED", command=cmd, fill=target.price if target else self.fill_price)]
        if stop:
            stop.state = "CANCELLED"
            events.append(self._event("ORDER_CANCELLED", command=cmd, order_id=stop.order_id))
        if target:
            target.state = "FILLED"
        self.position = FakePosition(instrument=self.instrument)
        events.append(self._event("POSITION_FLAT", command=cmd))
        self.events.extend(events)
        return events

    def fill_stop(self, command: Command | None = None) -> list[Event]:
        cmd = command or (self.submitted_commands[-1] if self.submitted_commands else Command("FLATTEN", "x"))
        stop = next((o for o in self.orders.values() if o.kind == "STOP"), None)
        target = next((o for o in self.orders.values() if o.kind == "TARGET"), None)
        events = [self._event("STOP_FILLED", command=cmd, fill=stop.price if stop else self.fill_price)]
        if target:
            target.state = "CANCELLED"
            events.append(self._event("ORDER_CANCELLED", command=cmd, order_id=target.order_id))
        if stop:
            stop.state = "FILLED"
        self.position = FakePosition(instrument=self.instrument)
        events.append(self._event("POSITION_FLAT", command=cmd))
        self.events.extend(events)
        return events

    def inject_unexpected_position(self, side: str = "LONG", quantity: int = 1) -> None:
        self.position = FakePosition(side=side, quantity=quantity, instrument=self.instrument, average_price=self.fill_price)

    def inject_orphan_order(self) -> None:
        oid = "orphan-" + uuid.uuid4().hex[:8]
        self.orders[oid] = FakeOrder(oid, "ORPHAN", "SELL", 1)

    def _enter(self, command: Command) -> list[Event]:
        if self.reject_next_entry:
            self.reject_next_entry = False
            return [self._event("ORDER_REJECTED", command=command, reason="BROKER_REJECT")]
        if self.position.side != "FLAT":
            return [self._event("COMMAND_REJECTED", reason="REJECT_POSITION_OPEN", command=command)]

        oid = "NT-" + uuid.uuid4().hex[:10]
        self.orders[oid] = FakeOrder(oid, "ENTRY", command.side or command.command, command.quantity, "SUBMITTED")
        self.command_ids[command.command_id] = oid
        side = "LONG" if command.command == "ENTER_LONG" else "SHORT"
        events = [
            self._event("ORDER_RECEIVED", command=command, order_id=oid),
            self._event("ORDER_SUBMITTED", command=command, order_id=oid),
            self._event("ORDER_ACCEPTED", command=command, order_id=oid),
        ]
        if self.out_of_order_events:
            events = [events[2], events[0], events[1]]
        if self.partial_then_fill and command.quantity > 1:
            events.append(
                self._event(
                    "PARTIAL_FILL",
                    command=command,
                    order_id=oid,
                    fill=self.fill_price,
                    fill_qty=1,
                    remaining=command.quantity - 1,
                )
            )
        fill_qty = command.quantity
        events.append(
            self._event(
                "FILLED",
                command=command,
                order_id=oid,
                fill=self.fill_price,
                fill_qty=fill_qty,
                remaining=0,
            )
        )
        self.position = FakePosition(side=side, quantity=fill_qty, instrument=self.instrument, average_price=self.fill_price)
        events.append(self._position_event(command))
        self.events.extend(events)
        return events

    def _protect(self, command: Command) -> list[Event]:
        if self.protection_should_fail:
            return [self._event("PROTECTION_FAILURE", command=command, reason="PROTECTION_REJECT")]
        filled = self.position.quantity
        if filled < 1:
            return [self._event("PROTECTION_FAILURE", command=command, reason="NO_POSITION")]
        prot_qty = min(command.quantity, filled)
        if command.quantity > filled:
            return [self._event("COMMAND_REJECTED", reason="INVALID_QUANTITY", command=command)]
        stop_id = "NT-STOP-" + uuid.uuid4().hex[:8]
        tgt_id = "NT-TGT-" + uuid.uuid4().hex[:8]
        self.orders[stop_id] = FakeOrder(stop_id, "STOP", "PROTECT", prot_qty, "WORKING", command.stop_price)
        self.orders[tgt_id] = FakeOrder(tgt_id, "TARGET", "PROTECT", prot_qty, "WORKING", command.target_price)
        self.command_ids[command.command_id] = stop_id
        events = [
            self._event("STOP_WORKING", command=command, order_id=stop_id),
            self._event("TARGET_WORKING", command=command, order_id=tgt_id),
        ]
        if self.disconnected_after_protect:
            self.disconnect()
        self.events.extend(events)
        return events

    def _flatten(self, command: Command) -> list[Event]:
        for order in self.orders.values():
            if order.state == "WORKING":
                order.state = "CANCELLED"
        was_open = self.position.side != "FLAT"
        self.position = FakePosition(instrument=self.instrument)
        events = []
        if was_open:
            events.append(self._event("FILLED", command=command, fill=self.fill_price, fill_qty=1, remaining=0))
        events.append(self._event("POSITION_FLAT", command=command))
        self.events.extend(events)
        return events

    def _position_event(self, command: Command) -> Event:
        name = "POSITION_FLAT" if self.position.side == "FLAT" else "POSITION_UPDATE"
        return self._event(
            name,
            command=command,
            extra={"position_side": self.position.side, "position_qty": self.position.quantity},
        )

    def _event(
        self,
        name: str,
        *,
        command: Command | None = None,
        reason: str = "",
        order_id: str = "",
        fill: float | None = None,
        fill_qty: int | None = None,
        remaining: int | None = None,
        existing: str = "",
        extra: dict | None = None,
    ) -> Event:
        ev = Event(
            event=name,
            command_id=command.command_id if command else "",
            event_id=command.event_id if command else "",
            signal_id=command.signal_id if command else "",
            created_at_utc=_iso(),
            reason=reason,
            order_id=order_id,
            fill_price=fill,
            fill_quantity=fill_qty,
            remaining_quantity=remaining,
            account=self.account or self.expected_account,
            instrument=self.instrument,
            existing_order_state=existing,
            extra=extra or {},
        )
        return ev
