"""Phase74 live production stack — wraps frozen Phase73 TraderEngine."""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional

from phase74.execution.slippage_router import SlippageSimRouter
from phase73.logging.decision_logger import DecisionLogger
from phase73.logging.event_store import EventStore
from phase73.persistence.state import StatePersistence
from phase73.trader.engine import TraderEngine
from phase73.trader.entry_quality import evaluate_entry
from phase73.trader.fsm import TraderAction, TraderState
from phase73.webhook.schemas import PineSignal, WebhookReason
from phase74.config.loader import Phase74Config, verify_phase73_freeze
from phase74.contracts.mapping import load_contract_spec, validate_contract_for_order
from phase74.execution.idempotency import OrderIdempotencyStore
from phase74.execution.paper_broker import PaperBrokerAdapter
from phase74.journal.trade_journal import TradeJournal, TradeJournalEntry
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.quality.day_halt import (
    PropDayHalt,
    new_entries_blocked_session,
    seed_day_halt_from_paper_trades,
)
from phase74.quality.gates import QualityDecision, QualityGateConfig, evaluate_quality_gates
from phase74.quality.logger import QualitySkipLogger
from phase74.quality.range_lock import RangeLock, RangeLockConfig, seed_from_paper_trades
from phase74.quality.trail import TrailOverlay, TrailOverlayConfig
from phase74.safety.daily_session import DailySessionSafety
from phase73.execution.positions import PositionBook, PositionSnapshot
from phase73.risk.reconciliation import reconcile as p73_reconcile

log = logging.getLogger("phase74.stack")


def _keep_winner_past_hour(reason: str, mgmt, bar) -> bool:
    """A one-hour time stop does not apply once the trade is green."""
    if reason != "MAX_HOLD_60M" or mgmt is None or bar is None:
        return False
    if mgmt.side == "LONG":
        return float(bar.close) > float(mgmt.entry_price)
    if mgmt.side == "SHORT":
        return float(bar.close) < float(mgmt.entry_price)
    return False

# Opposite TAKE parks Phase73 in REVERSAL_WATCH_* and then on_bar ignores the stop.
# Auto-reverse is off, so snap back to the live side and keep managing.
_REVERSAL_WATCH_RESUME = {
    TraderState.REVERSAL_WATCH_LONG: TraderState.SHORT_ACTIVE,
    TraderState.REVERSAL_WATCH_SHORT: TraderState.LONG_ACTIVE,
}


class LiveStack:
    """Dress-rehearsal runtime: live data + secure webhook + paper/local sim + shadow mode."""

    def __init__(
        self,
        cfg: Phase74Config,
        market_data: StreamLiveDataProvider,
        execution_adapter: Optional[Any] = None,
    ) -> None:
        ok, errs = verify_phase73_freeze()
        if not ok:
            raise RuntimeError(f"PHASE73_ENGINE_FREEZE_FAILED: {errs}")

        self.cfg = cfg
        self.market_data = market_data
        self.execution_adapter = execution_adapter
        self.webhook_status = "NOT_STARTED"
        self._latency_samples: list[float] = []
        self._active_trade_id: str | None = None
        self._active_entry_atr: float = 0.0
        self._active_entry_risk: float = 0.0
        self._stop_points = float(cfg.section("risk").get("stop_points", 0) or 0)
        qg = cfg.section("quality_gates")
        self._quality_enabled = bool(qg.get("enabled", False))
        self._filter_signals = bool(qg.get("filter_signals", True))
        self._cdx_repeat_seconds = int(qg.get("cdx_repeat_seconds", 0) or 0)
        self._last_cdx_direction: str | None = None
        self._last_cdx_time: datetime | None = None
        self._allow_globex_entries = bool(qg.get("allow_globex_entries", False))
        self._quality_cfg = QualityGateConfig.from_dict(qg)
        self._quality_log = QualitySkipLogger(cfg.log_dir) if self._quality_enabled else None
        self._day_halt = (
            PropDayHalt(
                max_losers=int(qg.get("day_max_losers", 2)),
                max_loss_dollars=float(qg.get("day_max_loss_dollars", 400.0)),
                max_winners=int(qg.get("day_max_winners", 2)),
                big_win_dollars=float(qg.get("day_big_win_dollars", 500.0)),
                giveback_arm_dollars=float(qg.get("day_giveback_arm_dollars", 400.0)),
                giveback_dollars=float(qg.get("day_giveback_dollars", 300.0)),
                point_value=float(qg.get("nq_point_value", 20.0)),
            )
            if self._quality_enabled
            else None
        )
        if self._day_halt is not None:
            seed_day_halt_from_paper_trades(
                self._day_halt,
                cfg.log_dir / "paper_trades.csv",
                audit_path=cfg.log_dir.parent.parent / "phase85" / "logs" / "audit.jsonl",
            )
        to = cfg.section("trail_overlay")
        self._trail_enabled = bool(to.get("enabled", False))
        self._trail_cfg = TrailOverlayConfig.from_dict(to)
        self._trail: TrailOverlay | None = None
        rl = cfg.section("range_lock")
        self.range_lock = RangeLock(
            RangeLockConfig.from_dict(rl),
            path=cfg.log_dir / "range_lock.json",
        )
        self._trade_hi: float | None = None
        self._trade_lo: float | None = None

        p73 = cfg.to_phase73_config()
        log_dir = cfg.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        self.contract = load_contract_spec(cfg.raw)
        sim = cfg.section("simulation")
        inner = SlippageSimRouter(
            entry_slippage_ticks=float(sim.get("entry_slippage_ticks", 1.0)),
            exit_slippage_ticks=float(sim.get("exit_slippage_ticks", 1.0)),
            tick_size=self.contract.tick_size,
        )
        self.broker = PaperBrokerAdapter(
            paper_mode=cfg.paper_mode,
            contract=self.contract,
            protective_orders=str(cfg.section("broker").get("protective_orders", "CLIENT_SIDE_PROTECTION")),
            inner=inner,
        )
        self.broker.connect()
        self.idempotency = OrderIdempotencyStore(Path(str(cfg.raw.get("persistence", {}).get("idempotency_file", log_dir / "order_idempotency.jsonl"))))
        self.journal = TradeJournal(log_dir)
        self.daily = DailySessionSafety(float(cfg.section("safety").get("daily_loss_limit", 500)))

        state_path = Path(str(cfg.raw.get("persistence", {}).get("state_file", log_dir / "trader_state.json")))
        self.engine = TraderEngine(
            cfg=p73,
            market_data=market_data,
            router=self.broker.inner,  # engine uses inner sim; broker wraps for reconciliation
            logger=DecisionLogger(log_dir),
            events=EventStore(log_dir),
            persistence=StatePersistence(state_path),
        )
        self._patch_engine_broker_submit()
        seed_from_paper_trades(self.range_lock, cfg.log_dir / "paper_trades.csv")

    def _with_live_atr(self, signal: PineSignal) -> PineSignal:
        """Prefer NT-computed ATR over Pine webhook placeholder (often 1.0)."""
        try:
            live_atr = float(self.market_data.atr())
        except (TypeError, ValueError, AttributeError):
            live_atr = 0.0
        if live_atr > 0 and signal.atr <= 1.5:
            return replace(signal, atr=live_atr)
        return signal

    def _patch_engine_broker_submit(self) -> None:
        """Route engine orders through PaperBrokerAdapter without modifying Phase73 engine source."""
        original_execute = self.engine._execute_entry
        original_exit = self.engine._execute_exit

        def execute_entry(signal, state_before, take_action):
            if self.cfg.shadow_mode:
                entry = evaluate_entry(signal, self.market_data, self.engine.cfg, position_side=self.engine.book.internal.side)
                action = "WOULD_ENTER" if entry.action in (TraderAction.TAKE_LONG, TraderAction.TAKE_SHORT) else f"WOULD_{entry.action.value}"
                self.engine.events.log_error({"shadow": action, "signal_id": signal.signal_id, "reason": entry.reason})
                log.info("SHADOW %s signal=%s reason=%s", action, signal.signal_id, entry.reason)
                self.engine.state = TraderState.FLAT
                self.engine.pending_signal = None
                return {"ok": True, "shadow": True, "action": action}
            if not self._pre_entry_checks(signal):
                self.engine.state = TraderState.FLAT
                self.engine.pending_signal = None
                return {"ok": False, "reason": "PRE_ENTRY_BLOCKED"}
            bar = self.market_data.latest_bar()
            if bar is None:
                return {"ok": False, "reason": "NO_BAR"}
            action_name = "MARKET_BUY" if signal.direction == "LONG" else "MARKET_SELL"
            if self.idempotency.seen(signal.signal_id, action_name):
                return {"ok": False, "reason": "ORDER_IDEMPOTENT_DUPLICATE"}
            signal = self._with_live_atr(signal)
            result = original_execute(signal, state_before, take_action)
            if result.get("ok") and self.engine.mgmt is not None:
                self._apply_fixed_stop()
            if result.get("ok") and result.get("fill_price") is not None:
                from phase73.execution.orders import Order, OrderSide

                side = OrderSide.BUY if signal.direction == "LONG" else OrderSide.SELL
                order = Order.new(action_name, side, 1, self.cfg.symbol, signal.signal_id)
                self.broker.submit(order, result["fill_price"])
                self.idempotency.record(signal.signal_id, action_name, order_id=order.order_id)
                risk = self._active_entry_risk or self.engine.cfg.stop_atr * signal.atr
                slip = self.broker.record_slippage(signal.signal_price, result["fill_price"], risk)
                trade_id = str(uuid.uuid4())
                self._active_trade_id = trade_id
                self._active_entry_atr = signal.atr
                target_px = self.engine.mgmt.target_price if self.engine.mgmt else 0
                self.journal.open_trade(
                    TradeJournalEntry(
                        trade_id=trade_id,
                        pine_signal_id=signal.signal_id,
                        direction=signal.direction,
                        signal_timestamp=signal.signal_time_utc.isoformat(),
                        signal_price=signal.signal_price,
                        entry_timestamp=bar.timestamp.isoformat(),
                        fill_price=result["fill_price"],
                        atr=signal.atr,
                        stop=self.engine.mgmt.stop_price if self.engine.mgmt else 0,
                        target=target_px,
                        signal_to_fill_ms=self.engine.last_latency.total_signal_to_fill_ms,
                        slippage_points=slip.get("slippage_points", 0),
                        slippage_ticks=slip.get("slippage_ticks", 0),
                        slippage_R=slip.get("slippage_R", 0),
                    )
                )
                if self._trail_enabled and self.engine.mgmt is not None:
                    self._trail = TrailOverlay(self._trail_cfg)
                    self._trail.hide_m0_target(self.engine.mgmt)
                    self.engine.book.internal.target_price = self.engine.mgmt.target_price
                fill_px = float(result["fill_price"])
                self._trade_hi = fill_px
                self._trade_lo = fill_px
                rejected = self._route_nt_entry(signal, fill_px)
                if rejected:
                    self._void_rejected_paper_entry(trade_id)
                    log.warning("void paper entry NT rejected reason=%s signal=%s", rejected, signal.signal_id)
                    return {"ok": False, "reason": rejected}
            return result

        def execute_exit(state_before, exit_dec, bar):
            trade_id = self._active_trade_id
            entry_atr = self._active_entry_atr
            mgmt = self.engine.mgmt
            if _keep_winner_past_hour(getattr(exit_dec, "reason", ""), mgmt, bar):
                log.info("hold past 60m while in profit close=%s", getattr(bar, "close", None))
                return {"ok": True, "holding": True}
            result = original_exit(state_before, exit_dec, bar)
            if result.get("ok"):
                self.broker.broker_position.side = "FLAT"
                if trade_id and mgmt:
                    exit_px = float(exit_dec.exit_price or bar.close)
                    risk = self._active_entry_risk or self.engine.cfg.stop_atr * entry_atr
                    move = (exit_px - mgmt.entry_price) if mgmt.side == "LONG" else (mgmt.entry_price - exit_px)
                    gross_r = move / risk if risk > 0 else 0.0
                    hold_min = (bar.timestamp - mgmt.entry_time).total_seconds() / 60.0
                    extra = {
                        "banked_2r5": bool(self._trail.banked) if self._trail else False,
                        "breakeven_armed": bool(self._trail.breakeven_armed) if self._trail else False,
                        "locked_r": self._trail_cfg.lock_stop_r if self._trail and self._trail.banked else "",
                    }
                    self.journal.close_trade(
                        trade_id,
                        exit_timestamp=bar.timestamp.isoformat(),
                        exit_price=exit_px,
                        exit_reason=exit_dec.reason,
                        gross_R=gross_r,
                        net_R=gross_r,
                        hold_time_minutes=hold_min,
                        MFE=mgmt.mfe_r,
                        MAE=mgmt.mae_r,
                        extra=extra,
                    )
                    if self._day_halt is not None:
                        self._day_halt.record_closed(
                            gross_r, bar.timestamp, dollars=move * 20.0
                        )
                    self._expand_trade_range(bar)
                    arm_stop_only = self.range_lock.cfg.arm_on == "stop"
                    if self._trade_hi is not None and self._trade_lo is not None:
                        if not arm_stop_only or gross_r <= 0:
                            self.range_lock.arm(self._trade_hi, self._trade_lo, bar.timestamp)
                    self._trade_hi = None
                    self._trade_lo = None
                    self._trail = None
                    self._active_trade_id = None
                    self._active_entry_atr = 0.0
                    self._active_entry_risk = 0.0
                    self._route_nt_flatten()
            return result

        self.engine._execute_entry = execute_entry  # type: ignore[method-assign]
        self.engine._execute_exit = execute_exit  # type: ignore[method-assign]

    def _expand_trade_range(self, bar) -> None:
        if bar is None:
            return
        hi = float(bar.high)
        lo = float(bar.low)
        self._trade_hi = hi if self._trade_hi is None else max(self._trade_hi, hi)
        self._trade_lo = lo if self._trade_lo is None else min(self._trade_lo, lo)

    def _cdx_repeat_reason(self, signal: PineSignal) -> str:
        if self._cdx_repeat_seconds <= 0 or self._last_cdx_direction is None or self._last_cdx_time is None:
            return ""
        if signal.direction != self._last_cdx_direction:
            return ""
        age = (signal.signal_time_utc - self._last_cdx_time).total_seconds()
        if 0 <= age < self._cdx_repeat_seconds:
            return "SKIP_CDX_REPEAT"
        return ""

    def _remember_cdx(self, signal: PineSignal) -> None:
        self._last_cdx_direction = signal.direction
        self._last_cdx_time = signal.signal_time_utc

    def _pre_entry_checks(self, signal: PineSignal) -> bool:
        if self._day_halt is not None and self._day_halt.should_halt_new_entries(signal.signal_time_utc):
            log.warning("%s", self._day_halt.reason)
            return False
        blocked = self._nt_entry_block_reason()
        if blocked:
            log.warning("NT entry blocked reason=%s signal=%s", blocked, signal.signal_id)
            return False
        if self.cfg.kill_switch or self.daily.should_halt(int(self.cfg.section("safety").get("max_consecutive_errors", 5))):
            log.warning("HALT_NEW_ENTRIES")
            return False
        err = validate_contract_for_order(self.contract)
        if err:
            log.error(err)
            return False
        self.engine.book.broker = self.broker.get_position()
        if p73_reconcile(self.engine.book):
            log.error("POSITION_MISMATCH")
            self.engine.state = TraderState.HALTED
            return False
        if self.market_data.health().state.value not in ("DATA_HEALTHY",):
            log.warning("DATA_UNHEALTHY %s", self.market_data.health().state.value)
            return False
        if not self.cfg.trading_enabled and not self.cfg.shadow_mode:
            return False
        return True

    def _apply_fixed_stop(self) -> None:
        """Use a fixed point stop. R multiples stay on that distance."""
        points = self._stop_points
        mgmt = self.engine.mgmt
        if points <= 0 or mgmt is None:
            return
        target_r = self._trail_cfg.profit_cap_r or float(self.engine.cfg.target_r)
        if mgmt.side == "LONG":
            mgmt.stop_price = mgmt.entry_price - points
            mgmt.target_price = mgmt.entry_price + target_r * points
        elif mgmt.side == "SHORT":
            mgmt.stop_price = mgmt.entry_price + points
            mgmt.target_price = mgmt.entry_price - target_r * points
        else:
            return
        mgmt.risk = points
        self._active_entry_risk = points
        for snap in (self.engine.book.internal, self.engine.book.desired, self.engine.book.broker):
            if snap.side == mgmt.side:
                snap.stop_price = mgmt.stop_price
                snap.target_price = mgmt.target_price

    def _nt_entry_block_reason(self) -> str:
        """Block a new paper trade while NinjaTrader still has this position open."""
        adapter = self.execution_adapter
        if adapter is None:
            return ""
        try:
            routing = bool(adapter.cfg.routing_enabled())
        except AttributeError:
            return ""
        if not routing or not getattr(adapter.transport, "authenticated", False):
            return ""
        from phase85.execution.gates import blocks_new_entries
        from phase85.execution.state_machine import ExecutionState

        if not blocks_new_entries(adapter.state):
            return ""
        if adapter.state != ExecutionState.HALTED:
            adapter.query_position()
        if not blocks_new_entries(adapter.state):
            return ""
        return "REJECT_POSITION_OPEN"

    def _void_rejected_paper_entry(self, trade_id: str | None) -> None:
        """Drop a paper fill NinjaTrader refused so it cannot become a halt loss."""
        if trade_id:
            self.journal._open.pop(trade_id, None)
        self.engine.mgmt = None
        self.engine.book = PositionBook()
        self.engine.state = TraderState.FLAT
        self.engine.pending_signal = None
        self.broker.broker_position = PositionSnapshot()
        self._trail = None
        self._trade_hi = None
        self._trade_lo = None
        self._active_trade_id = None
        self._active_entry_atr = 0.0
        self._active_entry_risk = 0.0
        self.engine.persist()

    def _route_nt_entry(self, signal: PineSignal, fill_price: float) -> str:
        """Send the entry. Return a reject reason, or empty when the order was accepted or not routed."""
        adapter = self.execution_adapter
        if adapter is None:
            return ""
        try:
            routing = bool(adapter.cfg.routing_enabled())
        except AttributeError:
            routing = False
        if not routing:
            log.info("NT execution skip: routing disabled")
            return ""
        if not getattr(adapter.transport, "authenticated", False):
            log.warning("NT execution skip: CRTExecutionBridge not connected")
            return ""
        from phase85.execution.intent import ExecutionIntent
        from phase85.execution.state_machine import ExecutionState

        now = datetime.now(timezone.utc)
        intent = ExecutionIntent(
            side=signal.direction,
            quantity=1,
            instrument=str(adapter.cfg.expected_contract or "MNQ 12-26"),
            command_id=str(uuid.uuid4()),
            event_id=signal.signal_id,
            signal_id=signal.signal_id,
            expected_entry=float(fill_price),
            signal_atr=float(self._stop_points or signal.atr),
            signal_time=signal.signal_time_utc,
            webhook_received=now,
            decision_time=now,
            phase73_decision="TAKE",
        )
        result = adapter.request_entry(intent)
        log.info("NT execution entry allowed=%s reason=%s", result.allowed, result.reason)
        if not result.allowed:
            return result.reason or "NT_REJECTED"
        for ev in result.events or []:
            if ev.event in {"COMMAND_REJECTED", "ORDER_REJECTED"}:
                return ev.reason or ev.event
        if getattr(adapter, "state", None) == ExecutionState.FILLED_UNPROTECTED:
            prot = adapter.place_protection()
            log.info("NT execution protect allowed=%s reason=%s", prot.allowed, prot.reason)
        return ""

    def _route_nt_flatten(self) -> None:
        adapter = self.execution_adapter
        if adapter is None:
            return
        if getattr(adapter, "side", "FLAT") == "FLAT":
            return
        result = adapter.flatten()
        log.info("NT execution flatten allowed=%s reason=%s", result.allowed, result.reason)

    def _release_reversal_watch(self) -> None:
        if self.engine.cfg.auto_reverse_enabled:
            return
        resume = _REVERSAL_WATCH_RESUME.get(self.engine.state)
        if resume is None:
            return
        side = self.engine.book.internal.side
        if self.engine.mgmt is None or side not in ("LONG", "SHORT"):
            return
        expected = "SHORT" if resume == TraderState.SHORT_ACTIVE else "LONG"
        if side != expected:
            return
        log.info("release reversal watch %s -> %s", self.engine.state.value, resume.value)
        self.engine.state = resume
        self.engine.persist()

    def on_webhook_signal(self, signal: PineSignal, reason: WebhookReason, tracker: LatencyTracker) -> dict[str, Any]:
        if reason != WebhookReason.WEBHOOK_VALID:
            return {"ok": False, "reason": reason.value}
        if signal.pine_hash != self.cfg.pine_hash:
            return {"ok": False, "reason": "SIGNAL_HASH_MISMATCH"}
        globex_block = new_entries_blocked_session(
            signal.signal_time_utc,
            allow_globex_entries=self._allow_globex_entries,
        )
        if globex_block:
            if self._quality_log is not None:
                self._quality_log.log(
                    QualityDecision(decision="SKIP", reason=globex_block),
                    signal_id=signal.signal_id,
                    direction=signal.direction,
                )
            log.info("quality skip signal=%s reason=%s", signal.signal_id, globex_block)
            return {"ok": False, "reason": globex_block, "quality": globex_block}
        repeat = self._cdx_repeat_reason(signal)
        if repeat:
            if self._quality_log is not None:
                self._quality_log.log(
                    QualityDecision(decision="SKIP", reason=repeat),
                    signal_id=signal.signal_id,
                    direction=signal.direction,
                )
            log.info("quality skip signal=%s reason=%s", signal.signal_id, repeat)
            return {"ok": False, "reason": repeat, "quality": repeat}
        self._remember_cdx(signal)
        if self._quality_enabled and self._filter_signals:
            lookback = self._quality_cfg.lookback_bars
            bars = list(self.market_data.recent_bars(lookback))
            try:
                live_atr = float(self.market_data.atr())
            except (TypeError, ValueError, AttributeError):
                live_atr = 0.0
            if live_atr <= 0 and signal.atr > 1.5:
                live_atr = float(signal.atr)
            qdec = evaluate_quality_gates(bars, signal.direction, live_atr, self._quality_cfg)
            if self._quality_log is not None:
                self._quality_log.log(qdec, signal_id=signal.signal_id, direction=signal.direction)
            if qdec.decision == "SKIP":
                log.info("quality skip signal=%s reason=%s", signal.signal_id, qdec.reason)
                return {"ok": False, "reason": qdec.reason, "quality": qdec.reason}
        bar = self.market_data.latest_bar()
        if bar is not None:
            lock_reason = self.range_lock.evaluate(float(bar.close), signal.signal_time_utc)
            if lock_reason:
                qdec = QualityDecision(
                    decision="SKIP",
                    reason=lock_reason,
                    close=float(bar.close),
                    range_low=float(self.range_lock.low or 0.0),
                    range_high=float(self.range_lock.high or 0.0),
                )
                if self._quality_log is not None:
                    self._quality_log.log(qdec, signal_id=signal.signal_id, direction=signal.direction)
                log.info("quality skip signal=%s reason=%s", signal.signal_id, lock_reason)
                return {"ok": False, "reason": lock_reason, "quality": lock_reason}
        if self._day_halt is not None and self._day_halt.should_halt_new_entries(signal.signal_time_utc):
            log.warning("%s signal=%s", self._day_halt.reason, signal.signal_id)
            return {"ok": False, "reason": self._day_halt.reason}
        tracker.decision_at = datetime.now(timezone.utc)
        result = self.engine.on_webhook_signal(signal, reason)
        self._release_reversal_watch()
        tracker.order_submitted_at = datetime.now(timezone.utc)
        tracker.broker_ack_at = tracker.order_submitted_at
        tracker.fill_at = tracker.order_submitted_at if result.get("fill_price") else None
        lat = tracker.finalize()
        self._latency_samples.extend(tracker.samples)
        self.engine.events.log_signal({**signal.to_dict(), "latency": lat})
        return result

    def on_bar(self) -> dict[str, Any]:
        if self.execution_adapter is not None:
            try:
                healthy = self.market_data.health().state.value == "DATA_HEALTHY"
                self.execution_adapter.mark_data_healthy(healthy)
            except AttributeError:
                pass
        if self.broker.health().value == "DISCONNECTED" and self.engine.book.internal.side != "FLAT":
            self.engine.events.log_error({"critical": "BROKER_DISCONNECT_ACTIVE"})
        self._release_reversal_watch()
        bar = self.market_data.latest_bar()
        if self._trade_hi is not None:
            self._expand_trade_range(bar)
        if (
            self._trail is not None
            and self.engine.mgmt is not None
            and bar is not None
            and self.engine.state in (TraderState.LONG_ACTIVE, TraderState.SHORT_ACTIVE)
        ):
            trail_dec = self._trail.on_bar(self.engine.mgmt, bar)
            self.engine.book.internal.stop_price = self.engine.mgmt.stop_price
            if trail_dec is not None:
                return self.engine._execute_exit(self.engine.state.value, trail_dec, bar)
        return self.engine.on_bar()

    def tick(self) -> bool:
        """Advance live stream one closed bar."""
        if not self.market_data.advance():
            return False
        self.on_bar()
        return True

    def latency_distribution(self) -> dict:
        return LatencyTracker.distribution(self._latency_samples)
