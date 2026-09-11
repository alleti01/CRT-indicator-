"""Phase74 live production stack — wraps frozen Phase73 TraderEngine."""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

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
from phase74.quality.day_halt import PropDayHalt
from phase74.quality.gates import QualityGateConfig, evaluate_quality_gates
from phase74.quality.logger import QualitySkipLogger
from phase74.quality.trail import TrailOverlay, TrailOverlayConfig
from phase74.safety.daily_session import DailySessionSafety
from phase73.risk.reconciliation import reconcile as p73_reconcile

log = logging.getLogger("phase74.stack")


class LiveStack:
    """Dress-rehearsal runtime: live data + secure webhook + paper/local sim + shadow mode."""

    def __init__(self, cfg: Phase74Config, market_data: StreamLiveDataProvider) -> None:
        ok, errs = verify_phase73_freeze()
        if not ok:
            raise RuntimeError(f"PHASE73_ENGINE_FREEZE_FAILED: {errs}")

        self.cfg = cfg
        self.market_data = market_data
        self.webhook_status = "NOT_STARTED"
        self._latency_samples: list[float] = []
        self._active_trade_id: str | None = None
        self._active_entry_atr: float = 0.0
        qg = cfg.section("quality_gates")
        self._quality_enabled = bool(qg.get("enabled", False))
        self._quality_cfg = QualityGateConfig.from_dict(qg)
        self._quality_log = QualitySkipLogger(cfg.log_dir) if self._quality_enabled else None
        self._day_halt = (
            PropDayHalt(
                max_losers=int(qg.get("day_max_losers", 3)),
                max_loss_r=float(qg.get("day_max_loss_r", 2.0)),
            )
            if self._quality_enabled
            else None
        )
        to = cfg.section("trail_overlay")
        self._trail_enabled = bool(to.get("enabled", False))
        self._trail_cfg = TrailOverlayConfig.from_dict(to)
        self._trail: TrailOverlay | None = None

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
                return {"ok": False, "reason": "PRE_ENTRY_BLOCKED"}
            bar = self.market_data.latest_bar()
            if bar is None:
                return {"ok": False, "reason": "NO_BAR"}
            action_name = "MARKET_BUY" if signal.direction == "LONG" else "MARKET_SELL"
            if self.idempotency.seen(signal.signal_id, action_name):
                return {"ok": False, "reason": "ORDER_IDEMPOTENT_DUPLICATE"}
            signal = self._with_live_atr(signal)
            result = original_execute(signal, state_before, take_action)
            if result.get("ok") and result.get("fill_price") is not None:
                from phase73.execution.orders import Order, OrderSide

                side = OrderSide.BUY if signal.direction == "LONG" else OrderSide.SELL
                order = Order.new(action_name, side, 1, self.cfg.symbol, signal.signal_id)
                self.broker.submit(order, result["fill_price"])
                self.idempotency.record(signal.signal_id, action_name, order_id=order.order_id)
                risk = self.engine.cfg.stop_atr * signal.atr
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
            return result

        def execute_exit(state_before, exit_dec, bar):
            trade_id = self._active_trade_id
            entry_atr = self._active_entry_atr
            mgmt = self.engine.mgmt
            result = original_exit(state_before, exit_dec, bar)
            if result.get("ok"):
                self.broker.broker_position.side = "FLAT"
                if trade_id and mgmt:
                    exit_px = float(exit_dec.exit_price or bar.close)
                    risk = self.engine.cfg.stop_atr * entry_atr
                    move = (exit_px - mgmt.entry_price) if mgmt.side == "LONG" else (mgmt.entry_price - exit_px)
                    gross_r = move / risk if risk > 0 else 0.0
                    hold_min = (bar.timestamp - mgmt.entry_time).total_seconds() / 60.0
                    extra = {
                        "banked_2r5": bool(self._trail.banked) if self._trail else False,
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
                        self._day_halt.record_closed(gross_r)
                    self._trail = None
                    self._active_trade_id = None
                    self._active_entry_atr = 0.0
            return result

        self.engine._execute_entry = execute_entry  # type: ignore[method-assign]
        self.engine._execute_exit = execute_exit  # type: ignore[method-assign]

    def _pre_entry_checks(self, signal: PineSignal) -> bool:
        if self._day_halt is not None and self._day_halt.should_halt_new_entries():
            log.warning("%s", self._day_halt.reason)
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

    def on_webhook_signal(self, signal: PineSignal, reason: WebhookReason, tracker: LatencyTracker) -> dict[str, Any]:
        if reason != WebhookReason.WEBHOOK_VALID:
            return {"ok": False, "reason": reason.value}
        if signal.pine_hash != self.cfg.pine_hash:
            return {"ok": False, "reason": "SIGNAL_HASH_MISMATCH"}
        if self._quality_enabled:
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
        if self._day_halt is not None and self._day_halt.should_halt_new_entries():
            log.warning("%s signal=%s", self._day_halt.reason, signal.signal_id)
            return {"ok": False, "reason": self._day_halt.reason}
        tracker.decision_at = datetime.now(timezone.utc)
        result = self.engine.on_webhook_signal(signal, reason)
        tracker.order_submitted_at = datetime.now(timezone.utc)
        tracker.broker_ack_at = tracker.order_submitted_at
        tracker.fill_at = tracker.order_submitted_at if result.get("fill_price") else None
        lat = tracker.finalize()
        self._latency_samples.extend(tracker.samples)
        self.engine.events.log_signal({**signal.to_dict(), "latency": lat})
        return result

    def on_bar(self) -> dict[str, Any]:
        if self.broker.health().value == "DISCONNECTED" and self.engine.book.internal.side != "FLAT":
            self.engine.events.log_error({"critical": "BROKER_DISCONNECT_ACTIVE"})
        bar = self.market_data.latest_bar()
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
