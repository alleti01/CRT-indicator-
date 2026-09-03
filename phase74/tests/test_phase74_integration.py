"""Phase74 integration tests P74-01 through P74-26."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase73.replay.runner import _synthetic_bars
from phase73.trader.fsm import TraderState, TraderAction
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase73.webhook.validator import validate_webhook_payload
from phase74.config.loader import Phase74Config, load_phase74_config, verify_phase73_freeze
from phase74.contracts.mapping import load_contract_spec, validate_contract_for_order
from phase74.execution.idempotency import OrderIdempotencyStore
from phase74.execution.paper_broker import PaperBrokerAdapter, BrokerHealth
from phase74.market_data.bar_finalizer import BarLifecycle
from phase74.market_data.live_provider import StreamLiveDataProvider, compare_replay_live_parity
from phase74.runtime.live_stack import LiveStack
from phase74.safety.daily_session import DailySessionSafety
from phase74.safety.emergency import emergency_flatten
from phase74.webhook.secure_receiver import SecureWebhookReceiver
from phase74.latency.tracker import LatencyTracker


def p74_cfg(**mode) -> Phase74Config:
    raw = copy.deepcopy(load_phase74_config().raw)
    raw.setdefault("mode", {}).update({"shadow_mode": False, "paper_mode": True, "trading_enabled": True, **mode})
    raw.setdefault("contracts", {})["contract_month"] = "202609"
    raw.setdefault("logging", {})["log_dir"] = tempfile.mkdtemp()
    raw.setdefault("persistence", {})["state_file"] = str(Path(raw["logging"]["log_dir"]) / "state.json")
    raw["persistence"]["idempotency_file"] = str(Path(raw["logging"]["log_dir"]) / "idempotency.jsonl")
    return Phase74Config(raw=raw)


class Phase74IntegrationTests(unittest.TestCase):
    def test_p74_01_live_replay_parity(self):
        df = _synthetic_bars(100)
        ok, errs = compare_replay_live_parity(df, n_bars=80)
        self.assertTrue(ok, errs[:5])

    def test_p74_02_duplicate_webhook(self):
        cfg = load_phase74_config().to_phase73_config()
        td = tempfile.TemporaryDirectory()
        recv = SecureWebhookReceiver(cfg, "secret", lambda s, r, t: None, deduplicator=__import__("phase73.webhook.deduplicator", fromlist=["SignalDeduplicator"]).SignalDeduplicator(Path(td.name) / "ids.jsonl"))
        p = make_test_signal().to_dict()
        hdrs = {"Authorization": "Bearer secret"}
        self.assertTrue(recv.handle_payload(p, headers=hdrs)[0])
        self.assertFalse(recv.handle_payload(p, headers=hdrs)[0])
        td.cleanup()

    def test_p74_03_stale_webhook(self):
        cfg = load_phase74_config().to_phase73_config()
        old = datetime.now(timezone.utc) - timedelta(seconds=500)
        p = make_test_signal(signal_time_utc=old, signal_bar_time_utc=old).to_dict()
        r = validate_webhook_payload(p, cfg)
        self.assertEqual(r.reason, WebhookReason.SIGNAL_STALE)

    def test_p74_04_bad_pine_hash(self):
        cfg = load_phase74_config().to_phase73_config()
        p = make_test_signal().to_dict()
        p["pine_hash"] = "bad"
        r = validate_webhook_payload(p, cfg)
        self.assertEqual(r.reason, WebhookReason.SIGNAL_HASH_MISMATCH)

    def test_p74_05_wrong_symbol(self):
        cfg = load_phase74_config().to_phase73_config()
        p = make_test_signal(symbol="ES").to_dict()
        r = validate_webhook_payload(p, cfg)
        self.assertEqual(r.reason, WebhookReason.SIGNAL_WRONG_SYMBOL)

    def test_p74_06_contract_mapping_failure(self):
        spec = load_contract_spec({"contracts": {"pine_symbol": "NQ", "contract_month": "UNRESOLVED"}})
        self.assertEqual(validate_contract_for_order(spec), "CONTRACT_MAPPING_UNRESOLVED")

    def test_p74_07_valid_long_paper_entry(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertEqual(stack.engine.state, TraderState.LONG_ACTIVE)

    def test_p74_08_valid_short_paper_entry(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertEqual(stack.engine.state, TraderState.SHORT_ACTIVE)

    def test_p74_09_fill_is_entry_basis(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close + 10)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertNotEqual(stack.engine.book.internal.entry_price, sig.signal_price)

    def test_p74_10_protective_stop_client_side(self):
        self.assertEqual(load_phase74_config().section("broker").get("protective_orders"), "CLIENT_SIDE_PROTECTION")

    def test_p74_11_target_management(self):
        from phase73.trader.management import build_management, evaluate_exit
        from phase73.config.loader import load_config
        from phase73.market_data.bar import Bar
        cfg73 = load_config()
        mgmt = build_management("LONG", 20000, 10, cfg73, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, mgmt.target_price + 1, 19999, mgmt.target_price)
        ex = evaluate_exit(mgmt, bar, cfg73, datetime.now(timezone.utc))
        self.assertEqual(ex.action.value, "EXIT_PROFIT")

    def test_p74_12_timeout(self):
        from phase73.trader.management import build_management, evaluate_exit
        from phase73.config.loader import load_config
        from phase73.market_data.bar import Bar
        cfg73 = load_config()
        et = datetime.now(timezone.utc) - timedelta(minutes=61)
        mgmt = build_management("LONG", 20000, 10, cfg73, et)
        bar = Bar(datetime.now(timezone.utc), 20000, 20005, 19995, 20001)
        ex = evaluate_exit(mgmt, bar, cfg73, datetime.now(timezone.utc))
        self.assertEqual(ex.action.value, "EXIT_TIME")

    def test_p74_13_broker_rejection(self):
        broker = PaperBrokerAdapter(paper_mode=False, contract=load_contract_spec({"contracts": {"contract_month": "202609"}}))
        from phase73.execution.orders import Order, OrderSide
        o = Order.new("MARKET_BUY", OrderSide.BUY, 1, "NQ")
        broker.connect()
        o2, fill = broker.submit(o, 20000)
        self.assertIsNone(fill)
        self.assertEqual(o2.reject_reason, "EXECUTION_MODE_UNVERIFIED")

    def test_p74_14_broker_timeout(self):
        broker = PaperBrokerAdapter(paper_mode=True, contract=load_contract_spec({"contracts": {"contract_month": "202609"}}))
        broker.connect()
        broker.disconnect()
        from phase73.execution.orders import Order, OrderSide
        o = Order.new("MARKET_BUY", OrderSide.BUY, 1, "NQ")
        o2, fill = broker.submit(o, 20000)
        self.assertIsNone(fill)
        self.assertEqual(o2.reject_reason, "BROKER_DISCONNECTED")

    def test_p74_17_data_disconnect_active(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        md.disconnect()
        r = stack.on_bar()
        self.assertEqual(md.health().state.value, "DATA_MISSING")

    def test_p74_18_broker_disconnect_active(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        stack.broker.disconnect()
        self.assertEqual(stack.broker.health().value, "DISCONNECTED")
        stack.on_bar()

    def test_p74_20_restart_active_short(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        stack.engine.persist()
        cfg2 = p74_cfg()
        cfg2.raw["persistence"]["state_file"] = cfg.raw["persistence"]["state_file"]
        cfg2.raw["logging"]["log_dir"] = cfg.raw["logging"]["log_dir"]
        stack2 = LiveStack(cfg2, md)
        self.assertEqual(stack2.engine.state, TraderState.SHORT_ACTIVE)

        td = tempfile.TemporaryDirectory()
        store = OrderIdempotencyStore(Path(td.name) / "id.jsonl")
        self.assertFalse(store.seen("sig1", "MARKET_BUY"))
        store.record("sig1", "MARKET_BUY", order_id="o1")
        self.assertTrue(store.seen("sig1", "MARKET_BUY"))
        td.cleanup()

    def test_p74_16_data_disconnect_flat(self):
        md = StreamLiveDataProvider(_synthetic_bars(10))
        md.connect()
        md.disconnect()
        self.assertEqual(md.health().state.value, "DATA_MISSING")

    def test_p74_19_restart_active_long(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        stack.engine.persist()
        cfg2 = p74_cfg()
        cfg2.raw["persistence"]["state_file"] = cfg.raw["persistence"]["state_file"]
        cfg2.raw["logging"]["log_dir"] = cfg.raw["logging"]["log_dir"]
        stack2 = LiveStack(cfg2, md)
        self.assertEqual(stack2.engine.state, TraderState.LONG_ACTIVE)

    def test_p74_21_position_mismatch(self):
        from phase73.execution.positions import PositionBook, PositionSnapshot
        from phase73.risk.reconciliation import reconcile
        b = PositionBook()
        b.internal = PositionSnapshot(side="LONG", quantity=1)
        b.broker = PositionSnapshot(side="FLAT")
        self.assertEqual(reconcile(b), TraderAction.POSITION_MISMATCH)

    def test_p74_22_emergency_flatten(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        r = emergency_flatten(stack)
        self.assertTrue(r.ok)

    def test_p74_23_daily_loss_halt(self):
        d = DailySessionSafety(daily_loss_limit=100)
        d.record_realized(-2, 100)
        self.assertTrue(d.should_halt(5))

    def test_p74_24_kill_switch(self):
        cfg = p74_cfg()
        os.environ["PHASE74_KILL_SWITCH"] = "1"
        md = StreamLiveDataProvider(_synthetic_bars(20))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        r = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        os.environ["PHASE74_KILL_SWITCH"] = "0"
        self.assertFalse(r.get("ok", True) if isinstance(r, dict) else True)

    def test_p74_25_opposite_signal_while_active(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        stack.on_webhook_signal(make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close), WebhookReason.WEBHOOK_VALID, LatencyTracker())
        r = stack.on_webhook_signal(make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close), WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertEqual(r.get("action"), TraderAction.OPPOSITE_SIGNAL_RECEIVED.value)

    def test_p74_26_same_direction_duplicate(self):
        cfg = p74_cfg()
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        r = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertEqual(r.get("action"), TraderAction.SAME_DIRECTION_SIGNAL.value)

    def test_phase73_freeze_verified(self):
        ok, errs = verify_phase73_freeze()
        self.assertTrue(ok, errs)

    def test_bar_finalization_closed(self):
        t0 = datetime(2026, 8, 30, 21, 29, tzinfo=timezone.utc)
        lc = BarLifecycle.from_bar_open(t0, finalized_at=t0 + timedelta(minutes=1, seconds=2))
        self.assertTrue(lc.is_closed_at(t0 + timedelta(minutes=1)))

    def test_shadow_mode_no_position(self):
        cfg = p74_cfg(shadow_mode=True, trading_enabled=False)
        md = StreamLiveDataProvider(_synthetic_bars(30))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
        r = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertTrue(r.get("shadow"))
        self.assertEqual(stack.engine.state, TraderState.FLAT)


if __name__ == "__main__":
    unittest.main()
