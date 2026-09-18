"""NinjaTrader execution adapter. One path for SHADOW / SIM / FUNDED."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from phase85.config import Phase85Config
from phase85.execution.gates import GateContext, GateResult, blocks_new_entries, evaluate_entry_gates, shadow_would_enter
from phase85.execution.intent import ExecutionIntent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.execution.latency import LatencySample, LatencyTracker
from phase85.execution.m0_map import M0Protection, m0_from_actual_fill
from phase85.execution.state_machine import ExecutionState, ExecutionStateMachine, InvalidTransition
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge
from phase85.persistence.audit import AuditLog
from phase85.persistence.command_store import CommandStore
from phase85.persistence.ledger import ExecutionLedger, LedgerRow, safe_account_id
from phase85.protocol.messages import Command, Event, utc_now
from phase85.reconciliation.reconcile import BrokerSnapshot, ExpectedSnapshot, ReconciliationResult, reconcile_execution


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class AdapterResult:
    allowed: bool
    reason: str
    would_enter: bool = False
    events: list[Event] = field(default_factory=list)
    gate: GateResult | None = None
    command: Command | None = None
    m0: M0Protection | None = None


class NinjaTraderExecutionAdapter:
    def __init__(
        self,
        cfg: Phase85Config,
        transport: FakeExecutionBridge,
        *,
        kill: ExecutionKillSwitch | None = None,
    ) -> None:
        self.cfg = cfg
        self.transport = transport
        self.kill = kill or ExecutionKillSwitch(KillState.EXECUTION_DISABLED)
        self.fsm = ExecutionStateMachine()
        self.commands = CommandStore(cfg.command_store_path)
        self.ledger = ExecutionLedger(cfg.ledger_path)
        self.audit = AuditLog(cfg.audit_path)
        self.latency = LatencyTracker(cfg.latency_path)
        self.startup_reconciled = False
        self.position_reconciled = False
        self.orders_reconciled = False
        self.data_healthy = False
        self.sim_gate_pass = _sim_gate_pass(cfg)
        self.side = "FLAT"
        self.quantity = 0
        self.filled_qty = 0
        self.remaining_qty = 0
        self.actual_fill: float | None = None
        self.expected_entry: float | None = None
        self.signal_atr = 0.0
        self.stop_working = False
        self.target_working = False
        self.entry_order_id = ""
        self.stop_order_id = ""
        self.target_order_id = ""
        self.last_intent: ExecutionIntent | None = None
        self.last_m0: M0Protection | None = None
        self.last_reconcile: ReconciliationResult | None = None
        self.active_latency: LatencySample | None = None
        self.flatten_confirmed = False
        self.audit.write("EXECUTION_BRIDGE_STARTED", mode=cfg.execution_mode)

    @property
    def state(self) -> ExecutionState:
        return self.fsm.state

    def connect(self) -> bool:
        ok = self.transport.connect(self.cfg.execution_token)
        if ok:
            self.audit.write("EXECUTION_CONNECTED")
            self.audit.write("EXECUTION_AUTHENTICATED")
            if self.transport.account_verified and self.cfg.expected_account == self.transport.account:
                self.audit.write("ACCOUNT_VERIFIED", account=safe_account_id(self.transport.account))
            if self.cfg.execution_mode == "FUNDED" and self.cfg.funded_account_verified:
                self.audit.write("FUNDED_ACCOUNT_VERIFIED", account=safe_account_id(self.cfg.allowed_funded_account))
            if self.transport.contract_verified:
                self.audit.write("CONTRACT_VERIFIED", instrument=self.transport.instrument)
        return ok

    def mark_data_healthy(self, healthy: bool) -> None:
        self.data_healthy = healthy

    def startup_reconcile(self) -> ReconciliationResult:
        snap = self._broker_snapshot()
        expected = self._expected_snapshot()
        result = reconcile_execution(expected, snap)
        self.last_reconcile = result
        if result.ok:
            self.startup_reconciled = True
            self.position_reconciled = True
            self.orders_reconciled = True
            self.audit.write("POSITION_RECONCILED", side=snap.side, qty=snap.quantity)
            self.audit.write("ORDERS_RECONCILED", unexpected=snap.unexpected_orders)
            if self.cfg.execution_mode == "SIM":
                self.audit.write("EXECUTION_READY_SIM")
            if self.cfg.execution_mode == "FUNDED" and self.sim_gate_pass:
                self.audit.write("EXECUTION_READY_FUNDED")
            if snap.side != "FLAT":
                self.side = snap.side
                self.quantity = snap.quantity
                self.filled_qty = snap.quantity
                if snap.working_stop and snap.working_target:
                    self._safe_transition(ExecutionState.POSITION_PROTECTED)
                    self.stop_working = True
                    self.target_working = True
                else:
                    self._safe_transition(ExecutionState.RECONCILIATION_REQUIRED)
                    self.startup_reconciled = False
                    self.position_reconciled = False
                    result = ReconciliationResult(False, "RECONCILIATION_REQUIRED", ["UNPROTECTED_OR_UNKNOWN"], True)
                    self.last_reconcile = result
            elif self.state in {ExecutionState.IDLE, ExecutionState.FLAT, ExecutionState.RECONCILIATION_REQUIRED}:
                if self.state == ExecutionState.RECONCILIATION_REQUIRED:
                    self._safe_transition(ExecutionState.IDLE)
                elif self.state == ExecutionState.FLAT:
                    self._safe_transition(ExecutionState.IDLE)
        else:
            self.startup_reconciled = False
            self.position_reconciled = False
            self.orders_reconciled = False
            self._safe_transition(ExecutionState.RECONCILIATION_REQUIRED)
            self.audit.write("RECONCILIATION_FAIL", mismatches=result.mismatches)
        return result

    def request_entry(self, intent: ExecutionIntent, *, now: datetime | None = None) -> AdapterResult:
        now = now or utc_now()
        self.last_intent = intent
        stale = _is_stale(intent.signal_time, now, self.cfg.stale_signal_seconds)
        ctx = self._gate_context(intent, stale=stale)
        gate = evaluate_entry_gates(ctx)

        if self.cfg.execution_mode == "SHADOW" or self.cfg.shadow_mode:
            would = shadow_would_enter(ctx)
            if would:
                self.audit.write("WOULD_ENTER", signal_id=intent.signal_id, side=intent.side)
            return AdapterResult(False, "WOULD_ENTER" if would else gate.reason, would_enter=would, gate=gate)

        if gate.allowed and blocks_new_entries(self.state) and self.state not in {ExecutionState.IDLE, ExecutionState.FLAT}:
            gate = GateResult(False, "REJECT_POSITION_OPEN", ["REJECT_POSITION_OPEN"])

        if not gate.allowed:
            self.audit.write("COMMAND_REJECTED", reason=gate.reason, signal_id=intent.signal_id)
            return AdapterResult(False, gate.reason, gate=gate)

        if self.commands.seen_command(intent.command_id):
            rec = self.commands.get(intent.command_id) or {}
            ev = Event(
                event="DUPLICATE_COMMAND",
                command_id=intent.command_id,
                signal_id=intent.signal_id,
                event_id=intent.event_id,
                reason="DUPLICATE_COMMAND",
                existing_order_state=str(rec.get("state", "")),
                order_id=str(rec.get("order_id", "")),
            )
            return AdapterResult(False, "DUPLICATE_COMMAND", events=[ev], gate=gate)

        if intent.signal_id and self.commands.seen_signal(intent.signal_id):
            return AdapterResult(False, "DUPLICATE_SIGNAL", gate=gate)
        if intent.event_id and self.commands.seen_event(intent.event_id):
            return AdapterResult(False, "DUPLICATE_SIGNAL", gate=gate)

        self.commands.record(
            command_id=intent.command_id,
            command=intent.command,
            signal_id=intent.signal_id,
            event_id=intent.event_id,
            state="SENT",
        )
        cmd = Command(
            command=intent.command,
            command_id=intent.command_id,
            event_id=intent.event_id,
            signal_id=intent.signal_id,
            created_at_utc=_iso(now),
            account=self.cfg.expected_account,
            instrument=self.cfg.expected_contract or self.transport.instrument,
            side=intent.side,
            quantity=intent.quantity,
        )
        self.expected_entry = intent.expected_entry
        self.signal_atr = intent.signal_atr
        self._safe_transition(ExecutionState.ENTRY_PENDING)
        self.audit.write("COMMAND_RECEIVED", command=cmd.command, command_id=cmd.command_id)
        self._open_ledger(intent, cmd, now)
        self.active_latency = LatencySample(
            command_id=intent.command_id,
            signal_id=intent.signal_id,
            t0_signal=intent.signal_time,
            t1_webhook=intent.webhook_received,
            t2_decision=intent.decision_time,
            t3_command=now,
            t4_bridge=now,
        )
        events = self.transport.send(cmd)
        self._apply_events(events)
        return AdapterResult(True, "ENTRY_COMMAND_SENT", events=events, gate=gate, command=cmd, m0=self.last_m0)

    def place_protection(self, *, quantity: int | None = None) -> AdapterResult:
        if self.actual_fill is None or self.filled_qty < 1:
            return AdapterResult(False, "NO_FILL")
        qty = quantity if quantity is not None else self.filled_qty
        if qty > self.filled_qty:
            return AdapterResult(False, "INVALID_QUANTITY")
        if self.last_m0 is None:
            self.last_m0 = m0_from_actual_fill(
                self.side,
                self.actual_fill,
                self.signal_atr,
                utc_now(),
                expected_entry=self.expected_entry,
                tick_size=self.cfg.tick_size,
            )
        intent = self.last_intent
        prot_id = f"prot-{uuid.uuid4()}"
        cmd = Command(
            command="PLACE_PROTECTION",
            command_id=prot_id,
            event_id=intent.event_id if intent else "",
            signal_id=intent.signal_id if intent else "",
            created_at_utc=_iso(utc_now()),
            account=self.cfg.expected_account,
            instrument=self.cfg.expected_contract or self.transport.instrument,
            side=self.side,
            quantity=qty,
            stop_price=self.last_m0.stop_price,
            target_price=self.last_m0.target_price,
        )
        if self.commands.seen_command(prot_id):
            return AdapterResult(False, "DUPLICATE_COMMAND")
        self.commands.record(command_id=prot_id, command="PLACE_PROTECTION", signal_id=cmd.signal_id, event_id=cmd.event_id)
        if self.state == ExecutionState.FILLED_UNPROTECTED:
            self._safe_transition(ExecutionState.PROTECTION_PENDING)
        if self.active_latency:
            self.active_latency.t9_protection_submit = utc_now()
        self.audit.write("PROTECTION_SUBMITTED", stop=self.last_m0.stop_price, target=self.last_m0.target_price)
        self.ledger.update_last(
            risk_R=self.last_m0.risk,
            stop_price=self.last_m0.stop_price,
            target_price=self.last_m0.target_price,
            slippage_ticks=self.last_m0.slippage_ticks,
            slippage_points=self.last_m0.slippage_points,
        )
        events = self.transport.send(cmd)
        self._apply_events(events)
        return AdapterResult(True, "PROTECTION_SUBMITTED", events=events, command=cmd, m0=self.last_m0)

    def flatten(self) -> AdapterResult:
        cmd_id = f"flat-{uuid.uuid4()}"
        cmd = Command(
            command="FLATTEN",
            command_id=cmd_id,
            created_at_utc=_iso(utc_now()),
            account=self.cfg.expected_account,
            instrument=self.cfg.expected_contract or self.transport.instrument,
            quantity=max(self.filled_qty, 1),
        )
        self.commands.record(command_id=cmd_id, command="FLATTEN")
        if self.state not in {ExecutionState.IDLE, ExecutionState.FLAT, ExecutionState.HALTED}:
            self._safe_transition(ExecutionState.FLATTENING)
        self.flatten_confirmed = False
        events = self.transport.send(cmd)
        self._apply_events(events)
        if not self.flatten_confirmed:
            return AdapterResult(False, "FLATTEN_UNCONFIRMED", events=events, command=cmd)
        return AdapterResult(True, "FLAT", events=events, command=cmd)

    def cancel_entry(self) -> AdapterResult:
        cmd = Command(
            command="CANCEL_ENTRY",
            command_id=f"cancel-{uuid.uuid4()}",
            created_at_utc=_iso(utc_now()),
            account=self.cfg.expected_account,
        )
        events = self.transport.send(cmd)
        self._apply_events(events)
        return AdapterResult(True, "CANCEL_ENTRY", events=events, command=cmd)

    def apply_external_events(self, events: list[Event]) -> None:
        self._apply_events(events)

    def _apply_events(self, events: list[Event]) -> None:
        for ev in events:
            try:
                self._apply_one(ev)
            except InvalidTransition:
                self.audit.write("INVALID_TRANSITION", source_event=ev.event, state=self.state.value)

    def _apply_one(self, ev: Event) -> None:
        name = ev.event
        if name == "DUPLICATE_COMMAND":
            return
        if name == "COMMAND_REJECTED":
            self.audit.write("COMMAND_REJECTED", reason=ev.reason)
            if self.state == ExecutionState.ENTRY_PENDING:
                self._safe_transition(ExecutionState.REJECTED)
                self._safe_transition(ExecutionState.IDLE)
            return
        if name == "ORDER_REJECTED":
            self.audit.write("ORDER_REJECTED", reason=ev.reason)
            if self.state in {ExecutionState.ENTRY_PENDING, ExecutionState.ENTRY_ACCEPTED}:
                self._safe_transition(ExecutionState.REJECTED)
                self._safe_transition(ExecutionState.IDLE)
            return
        if name == "ORDER_SUBMITTED":
            self.entry_order_id = ev.order_id or self.entry_order_id
            self.commands.update_order(ev.command_id, order_id=self.entry_order_id, state="SUBMITTED")
            self.audit.write("ORDER_SUBMITTED", order_id=self.entry_order_id)
            self.ledger.update_last(ninjatrader_order_id=self.entry_order_id, submit_time=ev.created_at_utc)
            if self.active_latency:
                self.active_latency.t5_submit = utc_now()
            return
        if name == "ORDER_ACCEPTED":
            if self.state == ExecutionState.ENTRY_PENDING:
                self._safe_transition(ExecutionState.ENTRY_ACCEPTED)
            self.audit.write("ORDER_ACCEPTED", order_id=ev.order_id)
            self.ledger.update_last(ack_time=ev.created_at_utc)
            if self.active_latency:
                self.active_latency.t6_ack = utc_now()
            return
        if name == "ORDER_RECEIVED":
            return
        if name == "PARTIAL_FILL":
            qty = ev.fill_quantity or 0
            self.filled_qty += qty
            self.remaining_qty = ev.remaining_quantity if ev.remaining_quantity is not None else max(0, self.quantity - self.filled_qty)
            if ev.fill_price is not None:
                self.actual_fill = ev.fill_price
            if self.state in {ExecutionState.ENTRY_PENDING, ExecutionState.ENTRY_ACCEPTED, ExecutionState.PARTIALLY_FILLED}:
                self._safe_transition(ExecutionState.PARTIALLY_FILLED)
            self.audit.write("PARTIAL_FILL", qty=self.filled_qty, remaining=self.remaining_qty)
            return
        if name == "FILLED":
            if ev.fill_quantity:
                self.filled_qty = max(self.filled_qty, ev.fill_quantity)
            if ev.fill_price is not None:
                self.actual_fill = ev.fill_price
            self.remaining_qty = ev.remaining_quantity if ev.remaining_quantity is not None else 0
            intent = self.last_intent
            if intent and self.state in {
                ExecutionState.ENTRY_PENDING,
                ExecutionState.ENTRY_ACCEPTED,
                ExecutionState.PARTIALLY_FILLED,
                ExecutionState.IDLE,
            }:
                self.side = intent.side
                self.quantity = self.filled_qty
                self._safe_transition(ExecutionState.FILLED_UNPROTECTED)
                if self.actual_fill is not None and self.signal_atr:
                    self.last_m0 = m0_from_actual_fill(
                        self.side,
                        self.actual_fill,
                        self.signal_atr,
                        utc_now(),
                        expected_entry=self.expected_entry,
                        tick_size=self.cfg.tick_size,
                    )
                self.audit.write("FILL", price=self.actual_fill, qty=self.filled_qty)
                self.ledger.update_last(
                    fill_time=ev.created_at_utc,
                    fill_price=self.actual_fill,
                    fill_quantity=self.filled_qty,
                )
                if self.active_latency:
                    if self.active_latency.t7_first_fill is None:
                        self.active_latency.t7_first_fill = utc_now()
                    self.active_latency.t8_final_fill = utc_now()
            return
        if name == "STOP_WORKING":
            self.stop_working = True
            self.stop_order_id = ev.order_id or self.stop_order_id
            self.ledger.update_last(stop_order_id=self.stop_order_id, stop_working_time=ev.created_at_utc)
            self._maybe_protected()
            return
        if name == "TARGET_WORKING":
            self.target_working = True
            self.target_order_id = ev.order_id or self.target_order_id
            self.ledger.update_last(target_order_id=self.target_order_id, target_working_time=ev.created_at_utc)
            self._maybe_protected()
            return
        if name == "PROTECTION_FAILURE":
            self._safe_transition(ExecutionState.PROTECTION_FAILURE)
            self.audit.write("PROTECTION_FAILURE", reason=ev.reason)
            self.kill.halt("PROTECTION_FAILURE")
            self.audit.write("EXECUTION_HALTED", reason="PROTECTION_FAILURE")
            self.flatten()
            return
        if name == "TARGET_FILLED":
            if self.state not in {ExecutionState.POSITION_PROTECTED, ExecutionState.EXIT_PENDING}:
                raise InvalidTransition(self.state, ExecutionState.EXIT_PENDING)
            self._safe_transition(ExecutionState.EXIT_PENDING)
            self.audit.write("TARGET_FILLED", price=ev.fill_price)
            self.ledger.update_last(exit_time=ev.created_at_utc, exit_price=ev.fill_price, exit_reason="TARGET")
            return
        if name == "STOP_FILLED":
            if self.state not in {ExecutionState.POSITION_PROTECTED, ExecutionState.EXIT_PENDING}:
                raise InvalidTransition(self.state, ExecutionState.EXIT_PENDING)
            self._safe_transition(ExecutionState.EXIT_PENDING)
            self.audit.write("STOP_FILLED", price=ev.fill_price)
            self.ledger.update_last(exit_time=ev.created_at_utc, exit_price=ev.fill_price, exit_reason="STOP")
            return
        if name == "POSITION_FLAT":
            self.side = "FLAT"
            self.quantity = 0
            self.filled_qty = 0
            self.stop_working = False
            self.target_working = False
            self.flatten_confirmed = True
            if self.state == ExecutionState.POSITION_PROTECTED:
                self._safe_transition(ExecutionState.EXIT_PENDING)
            if self.state == ExecutionState.PROTECTION_FAILURE:
                self._safe_transition(ExecutionState.FLATTENING)
            if self.state in {ExecutionState.EXIT_PENDING, ExecutionState.FLATTENING}:
                self._safe_transition(ExecutionState.FLAT)
            self.audit.write("POSITION_FLAT")
            self.ledger.update_last(final_position="FLAT", reconciliation_status="OK")
            if self.active_latency:
                self.latency.add(self.active_latency)
                self.active_latency = None
            if self.kill.state is KillState.EXECUTION_HALTED:
                if self.state == ExecutionState.FLAT:
                    self._safe_transition(ExecutionState.HALTED)
            elif self.state == ExecutionState.FLAT:
                self._safe_transition(ExecutionState.IDLE)
            return
        if name == "POSITION_UPDATE":
            self.side = str(ev.extra.get("position_side", self.side))
            self.quantity = int(ev.extra.get("position_qty", self.quantity) or 0)
            return
        if name == "ORDER_CANCELLED":
            return

    def _maybe_protected(self) -> None:
        if self.stop_working and self.target_working:
            if self.state == ExecutionState.PROTECTION_PENDING:
                self._safe_transition(ExecutionState.POSITION_PROTECTED)
            self.audit.write("PROTECTION_WORKING")
            if self.active_latency:
                self.active_latency.t10_protection_working = utc_now()

    def _safe_transition(self, dst: ExecutionState) -> None:
        if self.state == dst:
            return
        self.fsm.transition(dst)

    def _gate_context(self, intent: ExecutionIntent, *, stale: bool) -> GateContext:
        connected_account = self.transport.account if self.transport.authenticated else ""
        contract = self.cfg.expected_contract or self.transport.instrument
        account_ok = bool(
            self.cfg.expected_account
            and self.transport.account_verified
            and connected_account == self.cfg.expected_account
        )
        contract_ok = bool(self.transport.contract_verified and _root_ok(self.cfg, contract))
        return GateContext(
            cfg=self.cfg,
            kill=self.kill,
            phase73_decision=intent.phase73_decision,
            data_healthy=self.data_healthy,
            bridge_connected=self.transport.connected,
            bridge_authenticated=self.transport.authenticated,
            account_verified=account_ok,
            connected_account=connected_account,
            contract_verified=contract_ok,
            contract_name=contract,
            quantity=intent.quantity,
            command_duplicate=self.commands.seen_command(intent.command_id),
            signal_duplicate=self.commands.seen_signal(intent.signal_id),
            signal_stale=stale,
            position_reconciled=self.position_reconciled,
            orders_reconciled=self.orders_reconciled,
            startup_reconciled=self.startup_reconciled,
            open_strategy_positions=0 if self.side == "FLAT" else 1,
            existing_side=self.side,
            intended_side=intent.side,
            sim_gate_pass=self.sim_gate_pass,
            unresolved_halt=self.kill.state is KillState.EXECUTION_HALTED,
            unresolved_reconciliation=self.state == ExecutionState.RECONCILIATION_REQUIRED,
        )

    def _broker_snapshot(self) -> BrokerSnapshot:
        raw = self.transport.snapshot()
        return BrokerSnapshot(
            account=self.transport.account,
            instrument=str(raw.get("instrument", self.transport.instrument)),
            side=str(raw.get("side", "FLAT")),
            quantity=int(raw.get("quantity", 0) or 0),
            working_stop=bool(raw.get("working_stop")),
            working_target=bool(raw.get("working_target")),
            unexpected_orders=int(raw.get("unexpected_orders", 0) or 0),
            orphan_orders=int(raw.get("orphan_orders", 0) or 0),
            connected=bool(raw.get("connected")),
        )

    def _expected_snapshot(self) -> ExpectedSnapshot:
        prot = self.state == ExecutionState.POSITION_PROTECTED
        return ExpectedSnapshot(
            side=self.side if self.side else "FLAT",
            quantity=self.quantity,
            instrument=self.cfg.expected_contract or self.transport.instrument,
            protection_required=prot,
            expected_stop=prot,
            expected_target=prot,
        )

    def _open_ledger(self, intent: ExecutionIntent, cmd: Command, now: datetime) -> None:
        self.ledger.append(
            LedgerRow(
                event_id=intent.event_id,
                signal_id=intent.signal_id,
                command_id=intent.command_id,
                signal_time_utc=_iso(intent.signal_time),
                webhook_received_utc=_iso(intent.webhook_received),
                decision_time_utc=_iso(intent.decision_time),
                command_created_utc=_iso(now),
                direction=intent.side,
                instrument=cmd.instrument,
                quantity=intent.quantity,
                account_safe_id=safe_account_id(self.cfg.expected_account),
                expected_entry=intent.expected_entry,
                execution_mode=self.cfg.execution_mode,
            )
        )


def live_ready_config(
    tmp_dir,
    *,
    mode: str = "SIM",
    account: str = "SIM101",
    contract: str = "MNQ 12-26",
    funded_account: str = "",
    funded_verified: bool = False,
) -> Phase85Config:
    from phase85.config import load_phase85_config

    return load_phase85_config(
        overlay={
            "execution_mode": mode,
            "shadow_mode": False,
            "trading_enabled": True,
            "external_order_routing": True,
            "nt_execution_bridge_enabled": True,
            "expected_account": account,
            "allowed_funded_account": funded_account,
            "funded_account_verified": funded_verified,
            "expected_contract": contract,
            "persistence_dir": str(tmp_dir),
            "sim_gate_path": str(tmp_dir / "sim_activation_gate.json"),
            "_test_token": "unit-test-execution-token",
        },
        env=False,
    )


def make_intent(
    *,
    side: str = "LONG",
    command_id: str | None = None,
    signal_id: str = "sig-1",
    event_id: str = "evt-1",
    quantity: int = 1,
    expected_entry: float = 19999.0,
    signal_atr: float = 10.0,
    decision: str = "TAKE",
    signal_age_seconds: int = 5,
) -> ExecutionIntent:
    now = utc_now()
    from datetime import timedelta

    return ExecutionIntent(
        side=side,
        quantity=quantity,
        instrument="MNQ 12-26",
        command_id=command_id or str(uuid.uuid4()),
        event_id=event_id,
        signal_id=signal_id,
        expected_entry=expected_entry,
        signal_atr=signal_atr,
        signal_time=now - timedelta(seconds=signal_age_seconds),
        webhook_received=now - timedelta(seconds=2),
        decision_time=now,
        phase73_decision=decision,
    )


def _is_stale(signal_time: datetime | None, now: datetime, limit: int) -> bool:
    if signal_time is None:
        return True
    if signal_time.tzinfo is None:
        signal_time = signal_time.replace(tzinfo=timezone.utc)
    return (now - signal_time).total_seconds() > limit


def _root_ok(cfg: Phase85Config, contract: str) -> bool:
    root = (contract or "").upper().split()[0]
    if root == "NQ" and not cfg.allow_nq_execution:
        return False
    return root == cfg.allowed_instrument_root.upper()


def _sim_gate_pass(cfg: Phase85Config) -> bool:
    path = cfg.sim_gate_path
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("pass")) and str(data.get("verdict", "")) == "PHASE85_SIM_EXECUTION_PASS"
