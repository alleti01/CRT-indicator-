"""Production TraderEngine — single engine for replay and webhook."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from phase73.config.loader import Phase73Config
from phase73.execution.orders import Order, OrderSide, OrderState
from phase73.execution.positions import PositionBook, PositionSnapshot
from phase73.execution.sim_router import SimOrderRouter
from phase73.logging.decision_logger import DecisionLogger, DecisionRecord
from phase73.logging.event_store import EventStore
from phase73.market_data.base import MarketDataProvider
from phase73.market_data.bar import Bar
from phase73.persistence.state import PersistedState, StatePersistence
from phase73.risk.reconciliation import reconcile
from phase73.risk.safety import SafetyLayer
from phase73.trader.entry_quality import evaluate_entry
from phase73.trader.fsm import TraderAction, TraderState
from phase73.trader.management import ManagementState, build_management, evaluate_exit
from phase73.webhook.schemas import PineSignal, WebhookReason


@dataclass
class LatencyMetrics:
    pine_to_webhook_ms: float = 0.0
    webhook_to_decision_ms: float = 0.0
    decision_to_order_ms: float = 0.0
    order_to_fill_ms: float = 0.0
    total_signal_to_fill_ms: float = 0.0


@dataclass
class TraderEngine:
    cfg: Phase73Config
    market_data: MarketDataProvider
    router: SimOrderRouter
    logger: DecisionLogger
    events: EventStore
    persistence: StatePersistence
    safety: SafetyLayer = field(init=False)
    state: TraderState = TraderState.FLAT
    book: PositionBook = field(default_factory=PositionBook)
    mgmt: ManagementState | None = None
    pending_signal: PineSignal | None = None
    last_latency: LatencyMetrics = field(default_factory=LatencyMetrics)
    _decision_started: datetime | None = None
    _order_submitted: datetime | None = None

    def __post_init__(self) -> None:
        self.safety = SafetyLayer(self.cfg)
        self._restore()

    def _restore(self) -> None:
        ps = self.persistence.load()
        if not ps:
            return
        try:
            self.state = TraderState(ps.trader_state)
        except ValueError:
            self.state = TraderState.HALTED
        if ps.open_side in ("LONG", "SHORT") and ps.entry_price is not None and ps.signal_atr is not None:
            et = datetime.fromisoformat(ps.entry_time) if ps.entry_time else self.market_data.current_time()
            self.mgmt = build_management(ps.open_side, ps.entry_price, ps.signal_atr, self.cfg, et)
            self.mgmt.stop_price = ps.stop_price or self.mgmt.stop_price
            self.mgmt.target_price = ps.target_price or self.mgmt.target_price
            self.mgmt.mfe_r = ps.mfe_r
            self.mgmt.mae_r = ps.mae_r
            self.mgmt.bars_in_trade = ps.bars_in_trade
            snap = PositionSnapshot(
                side=ps.open_side,
                quantity=1,
                entry_price=ps.entry_price,
                stop_price=self.mgmt.stop_price,
                target_price=self.mgmt.target_price,
                entry_time=et,
                signal_id=ps.last_signal_id,
                mfe_r=ps.mfe_r,
                mae_r=ps.mae_r,
            )
            self.book.internal = snap
            self.book.broker = snap
            self.book.desired = snap
            self.state = TraderState.LONG_ACTIVE if ps.open_side == "LONG" else TraderState.SHORT_ACTIVE

    def persist(self) -> None:
        ps = PersistedState(
            trader_state=self.state.value,
            last_signal_id=self.pending_signal.signal_id if self.pending_signal else "",
            open_side=self.book.internal.side,
            entry_price=self.book.internal.entry_price,
            stop_price=self.book.internal.stop_price,
            target_price=self.book.internal.target_price,
            signal_atr=self.mgmt.signal_atr if self.mgmt else None,
            entry_time=self.book.internal.entry_time.isoformat() if self.book.internal.entry_time else "",
            mfe_r=self.mgmt.mfe_r if self.mgmt else 0.0,
            mae_r=self.mgmt.mae_r if self.mgmt else 0.0,
            bars_in_trade=self.mgmt.bars_in_trade if self.mgmt else 0,
            halted=self.state == TraderState.HALTED,
        )
        self.persistence.save(ps)

    def _log_decision(
        self,
        state_before: str,
        state_after: str,
        action: TraderAction,
        reason: str,
        signal: PineSignal | None = None,
        order: Order | None = None,
        fill_price: float | None = None,
        latency: LatencyMetrics | None = None,
    ) -> None:
        bar = self.market_data.latest_bar()
        health = self.market_data.health()
        pos = self.book.internal
        rec = DecisionRecord(
            timestamp_utc=DecisionLogger.now_iso(),
            market_timestamp=bar.timestamp.isoformat() if bar else "",
            signal_id=signal.signal_id if signal else "",
            symbol=self.cfg.symbol,
            state_before=state_before,
            state_after=state_after,
            pine_event=signal.event if signal else "",
            pine_direction=signal.direction if signal else "",
            pine_signal_price=signal.signal_price if signal else None,
            pine_atr=signal.atr if signal else None,
            current_price=bar.close if bar else None,
            current_atr=self.market_data.atr(),
            position=pos.side,
            entry_price=pos.entry_price,
            stop_price=pos.stop_price,
            target_price=pos.target_price,
            current_R=self.mgmt.current_r if self.mgmt else None,
            MFE_R=self.mgmt.mfe_r if self.mgmt else None,
            MAE_R=self.mgmt.mae_r if self.mgmt else None,
            bars_in_trade=self.mgmt.bars_in_trade if self.mgmt else 0,
            market_data_health=health.state.value,
            action=action.value,
            reason_code=reason,
            order_id=order.order_id if order else "",
            order_action=order.action if order else "",
            order_status=order.state.value if order else "",
            fill_price=fill_price,
            latency_ms=latency.total_signal_to_fill_ms if latency else None,
        )
        self.logger.log(rec)

    def on_webhook_signal(self, signal: PineSignal, reason: WebhookReason) -> dict[str, Any]:
        if reason != WebhookReason.WEBHOOK_VALID:
            return {"ok": False, "reason": reason.value}

        self.events.log_signal(signal.to_dict())
        state_before = self.state.value
        now = self.market_data.current_time()
        self._decision_started = now
        self.last_latency.pine_to_webhook_ms = (signal.received_at_utc - signal.signal_time_utc).total_seconds() * 1000

        mm = reconcile(self.book)
        if mm and self.cfg.section("safety").get("halt_on_position_mismatch", True):
            self.state = TraderState.HALTED
            self._log_decision(state_before, self.state.value, mm, "POSITION_MISMATCH", signal=signal)
            self.events.log_error({"reason": "POSITION_MISMATCH"})
            return {"ok": False, "reason": mm.value}

        if self.state in (TraderState.LONG_ACTIVE, TraderState.SHORT_ACTIVE):
            active = "LONG" if self.state == TraderState.LONG_ACTIVE else "SHORT"
            if signal.direction == active:
                self._log_decision(state_before, self.state.value, TraderAction.SAME_DIRECTION_SIGNAL, "dedupe", signal=signal)
                return {"ok": True, "action": TraderAction.SAME_DIRECTION_SIGNAL.value}
            self.state = (
                TraderState.REVERSAL_WATCH_SHORT if active == "LONG" else TraderState.REVERSAL_WATCH_LONG
            )
            self._log_decision(state_before, self.state.value, TraderAction.OPPOSITE_SIGNAL_RECEIVED, "opposite", signal=signal)
            if not self.cfg.auto_reverse_enabled:
                return {"ok": True, "action": TraderAction.OPPOSITE_SIGNAL_RECEIVED.value}
            # reverse path deferred in V1
            return {"ok": True, "action": TraderAction.OPPOSITE_SIGNAL_RECEIVED.value}

        safety = self.safety.check_new_entry()
        if not safety.trading_allowed:
            self._log_decision(state_before, self.state.value, TraderAction.HALT_NEW_ENTRIES, safety.reason, signal=signal)
            return {"ok": False, "reason": safety.reason}

        self.pending_signal = signal
        self.state = (
            TraderState.SIGNAL_LONG_RECEIVED if signal.direction == "LONG" else TraderState.SIGNAL_SHORT_RECEIVED
        )
        entry = evaluate_entry(signal, self.market_data, self.cfg, position_side=self.book.internal.side, now=now)
        self.last_latency.webhook_to_decision_ms = (now - signal.received_at_utc).total_seconds() * 1000

        if entry.action != TraderAction.TAKE_LONG and entry.action != TraderAction.TAKE_SHORT:
            self.state = TraderState.FLAT
            self.pending_signal = None
            self._log_decision(state_before, self.state.value, entry.action, entry.reason, signal=signal)
            return {"ok": False, "action": entry.action.value, "reason": entry.reason}

        return self._execute_entry(signal, state_before, entry.action)

    def _execute_entry(self, signal: PineSignal, state_before: str, take_action: TraderAction) -> dict[str, Any]:
        bar = self.market_data.latest_bar()
        if bar is None:
            self._log_decision(state_before, self.state.value, TraderAction.PASS_DATA_UNHEALTHY, "no bar", signal=signal)
            return {"ok": False, "reason": "no bar"}

        side = signal.direction
        order_side = OrderSide.BUY if side == "LONG" else OrderSide.SELL
        action_str: Any = "MARKET_BUY" if side == "LONG" else "MARKET_SELL"
        order = Order.new(action_str, order_side, 1, self.cfg.symbol, signal.signal_id)
        self._order_submitted = self.market_data.current_time()
        order, fill = self.router.submit(order, bar.close)
        self.events.log_order({"order_id": order.order_id, "state": order.state.value, "action": order.action})

        if fill is None:
            self.state = TraderState.FLAT
            self.pending_signal = None
            self.safety.record_error()
            self._log_decision(state_before, self.state.value, TraderAction.PASS_INVALID, order.reject_reason, signal=signal, order=order)
            return {"ok": False, "reason": order.reject_reason}

        self.last_latency.decision_to_order_ms = (
            (self._order_submitted - self._decision_started).total_seconds() * 1000 if self._decision_started else 0
        )
        self.last_latency.order_to_fill_ms = 0.0
        self.last_latency.total_signal_to_fill_ms = (
            (fill.filled_at - signal.signal_time_utc).total_seconds() * 1000
        )

        et = bar.timestamp
        self.mgmt = build_management(side, fill.price, signal.atr, self.cfg, et)
        snap = PositionSnapshot(
            side=side,
            quantity=1,
            entry_price=fill.price,
            stop_price=self.mgmt.stop_price,
            target_price=self.mgmt.target_price,
            entry_time=et,
            signal_id=signal.signal_id,
        )
        self.book.desired = snap
        self.book.internal = snap
        self.book.broker = snap
        self.state = TraderState.LONG_ACTIVE if side == "LONG" else TraderState.SHORT_ACTIVE
        self.pending_signal = None
        self.safety.record_success()
        self.events.log_fill({"fill_id": fill.fill_id, "price": fill.price, "order_id": order.order_id})
        self.events.log_position({"side": side, "entry_price": fill.price})
        self._log_decision(
            state_before,
            self.state.value,
            take_action,
            "FILLED",
            signal=signal,
            order=order,
            fill_price=fill.price,
            latency=self.last_latency,
        )
        self.persist()
        return {"ok": True, "action": take_action.value, "fill_price": fill.price}

    def on_bar(self, bar: Bar | None = None) -> dict[str, Any]:
        bar = bar or self.market_data.latest_bar()
        if bar is None:
            return {"ok": False}
        state_before = self.state.value
        if self.state not in (TraderState.LONG_ACTIVE, TraderState.SHORT_ACTIVE) or self.mgmt is None:
            self._log_decision(state_before, self.state.value, TraderAction.WATCH, "bar")
            return {"ok": True}

        now = self.market_data.current_time()
        exit_dec = evaluate_exit(self.mgmt, bar, self.cfg, now)
        if exit_dec is None:
            minutes = (now - self.mgmt.entry_time).total_seconds() / 60.0
            hold = TraderAction.HOLD_LONG if self.mgmt.side == "LONG" else TraderAction.HOLD_SHORT
            self.book.internal.mfe_r = self.mgmt.mfe_r
            self.book.internal.mae_r = self.mgmt.mae_r
            self.book.internal.current_r = self.mgmt.current_r
            self.book.internal.bars_in_trade = self.mgmt.bars_in_trade
            self.book.internal.minutes_in_trade = minutes
            self._log_decision(state_before, self.state.value, hold, "manage", fill_price=bar.close)
            self.persist()
            return {"ok": True, "holding": True}

        return self._execute_exit(state_before, exit_dec, bar)

    def _execute_exit(self, state_before: str, exit_dec, bar: Bar) -> dict[str, Any]:
        side = OrderSide.SELL if self.mgmt and self.mgmt.side == "LONG" else OrderSide.BUY
        order = Order.new("FLATTEN", side, 1, self.cfg.symbol)
        px = exit_dec.exit_price or bar.close
        order, fill = self.router.submit(order, px)
        self.events.log_order({"order_id": order.order_id, "state": order.state.value, "action": "FLATTEN"})
        if fill:
            self.events.log_fill({"fill_id": fill.fill_id, "price": fill.price, "reason": exit_dec.reason})

        self.mgmt = None
        self.book = PositionBook()
        self.state = TraderState.FLAT
        self._log_decision(state_before, self.state.value, exit_dec.action, exit_dec.reason, fill_price=px)
        self.persist()
        return {"ok": True, "exit": exit_dec.action.value, "reason": exit_dec.reason}

    def flatten_emergency(self) -> None:
        bar = self.market_data.latest_bar()
        if self.mgmt is None or bar is None:
            self.state = TraderState.FLAT
            return
        self._execute_exit(self.state.value, type("E", (), {"action": TraderAction.EXIT_FAILURE, "reason": "EMERGENCY", "exit_price": bar.close})(), bar)
