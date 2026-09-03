"""Phase74 live production stack — wraps frozen Phase73 TraderEngine."""
from __future__ import annotations

import copy
import logging
import uuid
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from phase73.execution.sim_router import SimOrderRouter
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

        p73 = cfg.to_phase73_config()
        log_dir = cfg.log_dir
        log_dir.mkdir(parents=True, exist_ok=True)

        self.contract = load_contract_spec(cfg.raw)
        self.broker = PaperBrokerAdapter(
            paper_mode=cfg.paper_mode,
            contract=self.contract,
            protective_orders=str(cfg.section("broker").get("protective_orders", "CLIENT_SIDE_PROTECTION")),
            inner=SimOrderRouter(),
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
            result = original_execute(signal, state_before, take_action)
            if result.get("ok") and result.get("fill_price") is not None:
                from phase73.execution.orders import Order, OrderSide

                side = OrderSide.BUY if signal.direction == "LONG" else OrderSide.SELL
                order = Order.new(action_name, side, 1, self.cfg.symbol, signal.signal_id)
                self.broker.submit(order, result["fill_price"])
                self.idempotency.record(signal.signal_id, action_name, order_id=order.order_id)
                risk = self.engine.cfg.stop_atr * signal.atr
                slip = self.broker.record_slippage(signal.signal_price, result["fill_price"], risk)
                self.journal.open_trade(
                    TradeJournalEntry(
                        trade_id=str(uuid.uuid4()),
                        pine_signal_id=signal.signal_id,
                        direction=signal.direction,
                        signal_timestamp=signal.signal_time_utc.isoformat(),
                        signal_price=signal.signal_price,
                        entry_timestamp=bar.timestamp.isoformat(),
                        fill_price=result["fill_price"],
                        atr=signal.atr,
                        stop=self.engine.mgmt.stop_price if self.engine.mgmt else 0,
                        target=self.engine.mgmt.target_price if self.engine.mgmt else 0,
                        signal_to_fill_ms=self.engine.last_latency.total_signal_to_fill_ms,
                        slippage_points=slip.get("slippage_points", 0),
                        slippage_ticks=slip.get("slippage_ticks", 0),
                        slippage_R=slip.get("slippage_R", 0),
                    )
                )
            return result

        def execute_exit(state_before, exit_dec, bar):
            result = original_exit(state_before, exit_dec, bar)
            if self.engine.mgmt is None and result.get("ok"):
                self.broker.broker_position.side = "FLAT"
            return result

        self.engine._execute_entry = execute_entry  # type: ignore[method-assign]
        self.engine._execute_exit = execute_exit  # type: ignore[method-assign]

    def _pre_entry_checks(self, signal: PineSignal) -> bool:
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
        return self.engine.on_bar()

    def tick(self) -> bool:
        """Advance live stream one closed bar."""
        if not self.market_data.advance():
            return False
        self.on_bar()
        return True

    def latency_distribution(self) -> dict:
        return LatencyTracker.distribution(self._latency_samples)
