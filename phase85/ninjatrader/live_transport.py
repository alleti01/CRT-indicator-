"""Async NinjaTrader transport: Python listens, AddOn connects, events arrive later."""
from __future__ import annotations

import logging
import threading
from typing import Any

from phase85.execution.state_machine import ExecutionState
from phase85.ninjatrader.execution_server import ExecutionBridgeServer
from phase85.protocol.messages import Command, Event

log = logging.getLogger("phase85.live_transport")


class LiveNtTransport:
    def __init__(
        self,
        *,
        expected_account: str,
        expected_instrument: str,
    ) -> None:
        self.expected_account = expected_account
        self.expected_instrument = expected_instrument
        self.connected = False
        self.authenticated = False
        self.account = ""
        self.instrument = ""
        self.account_verified = False
        self.contract_verified = False
        self.server: ExecutionBridgeServer | None = None
        self._adapter: Any = None
        self._lock = threading.Lock()
        self._side = "FLAT"
        self._quantity = 0
        self._working_stop = False
        self._working_target = False
        self._unexpected_orders = 0

    def attach_server(self, server: ExecutionBridgeServer) -> None:
        self.server = server

    def attach_adapter(self, adapter: Any) -> None:
        self._adapter = adapter

    def connect(self, token: str) -> bool:
        del token
        return self.authenticated

    def disconnect(self) -> None:
        self.handle_disconnect()
        if self.server is not None:
            self.server.stop()

    def send(self, command: Command) -> list[Event]:
        if self.server is None or not self.authenticated:
            return []
        self.server.send_command(command)
        return []

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "side": self._side,
                "quantity": self._quantity,
                "instrument": self.instrument or self.expected_instrument,
                "working_stop": self._working_stop,
                "working_target": self._working_target,
                "unexpected_orders": self._unexpected_orders,
                "orphan_orders": 0,
                "connected": self.connected and self.authenticated,
            }

    def handle_hello(self, account: str, instrument: str) -> None:
        with self._lock:
            self.connected = True
            self.authenticated = True
            self.account = account
            self.instrument = instrument or self.expected_instrument
            self.account_verified = bool(account and account == self.expected_account)
            self.contract_verified = bool(
                self.instrument and self.instrument == self.expected_instrument
            )
        log.info(
            "execution hello account=%s instrument=%s account_ok=%s contract_ok=%s",
            account,
            self.instrument,
            self.account_verified,
            self.contract_verified,
        )
        adapter = self._adapter
        if adapter is not None:
            adapter.audit.write(
                "EXECUTION_AUTHENTICATED",
                account=account,
                instrument=self.instrument,
            )
            adapter.startup_reconcile()

    def handle_disconnect(self) -> None:
        with self._lock:
            self.connected = False
            self.authenticated = False
            self.account_verified = False
            self.contract_verified = False
        log.warning("execution bridge disconnected")

    def handle_event(self, event: Event) -> None:
        with self._lock:
            self._apply_snapshot(event)
            adapter = self._adapter
        if adapter is None:
            return
        with self._lock:
            adapter.apply_external_events([event])
            if event.event == "FILLED" and adapter.state == ExecutionState.FILLED_UNPROTECTED:
                adapter.place_protection()

    def _apply_snapshot(self, event: Event) -> None:
        if event.account:
            self.account = event.account
        if event.instrument:
            self.instrument = event.instrument
        if event.event == "POSITION_FLAT":
            self._side = "FLAT"
            self._quantity = 0
            self._working_stop = False
            self._working_target = False
        elif event.event == "POSITION_UPDATE":
            self._side = str(event.extra.get("position_side", event.side or self._side))
            qty = event.extra.get("position_qty", event.quantity)
            if qty is not None:
                self._quantity = int(qty)
        elif event.event == "STOP_WORKING":
            self._working_stop = True
        elif event.event == "TARGET_WORKING":
            self._working_target = True
        elif event.event in {"STOP_FILLED", "TARGET_FILLED"}:
            if event.event == "STOP_FILLED":
                self._working_stop = False
            else:
                self._working_target = False
