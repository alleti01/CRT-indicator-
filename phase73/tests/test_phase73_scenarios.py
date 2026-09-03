"""Phase73 deterministic scenario tests T01–T24."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from phase73.config.loader import Phase73Config, load_config
from phase73.execution.orders import Order, OrderSide
from phase73.execution.positions import PositionBook, PositionSnapshot
from phase73.execution.sim_router import SimOrderRouter
from phase73.market_data.bar import Bar
from phase73.market_data.cache import BarCache
from phase73.market_data.health import DataHealth
from phase73.market_data.provider import ReplayDataProvider
from phase73.replay.runner import ReplayRunner, _synthetic_bars
from phase73.trader.fsm import TraderAction, TraderState
from phase73.trader.management import build_management, evaluate_exit
from phase73.webhook.deduplicator import SignalDeduplicator
from phase73.webhook.receiver import WebhookReceiver
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase73.webhook.validator import validate_webhook_payload
from phase73.tests.conftest_helpers import test_cfg, temp_runner
from phase73.risk.reconciliation import reconcile


class Phase73ScenarioTests(unittest.TestCase):
    def test_t01_valid_long(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            r = runner.inject_signal(sig)
            self.assertTrue(r["ok"])
            self.assertEqual(runner.engine.state, TraderState.LONG_ACTIVE)

    def test_t02_valid_short(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            r = runner.inject_signal(sig)
            self.assertTrue(r["ok"])
            self.assertEqual(runner.engine.state, TraderState.SHORT_ACTIVE)

    def test_t03_duplicate_webhook(self):
        cfg = test_cfg()
        td = tempfile.TemporaryDirectory()
        dedup = SignalDeduplicator(Path(td.name) / "ids.jsonl")
        seen = []

        def on_sig(s, r):
            seen.append(s.signal_id)

        recv = WebhookReceiver(cfg, on_sig, deduplicator=dedup)
        bar = _synthetic_bars(5).index[0]
        payload = make_test_signal("SIGNAL_LONG").to_dict()
        ok1, _, _ = recv.handle_payload(payload)
        ok2, reason, _ = recv.handle_payload(payload)
        td.cleanup()
        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertEqual(reason, WebhookReason.SIGNAL_DUPLICATE)

    def test_t04_stale_signal(self):
        cfg = test_cfg()
        old = datetime.now(timezone.utc) - timedelta(seconds=cfg.webhook_staleness_limit_seconds + 10)
        sig = make_test_signal("SIGNAL_LONG", signal_time_utc=old, signal_bar_time_utc=old)
        result = validate_webhook_payload(sig.to_dict(), cfg)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, WebhookReason.SIGNAL_STALE)

    def test_t05_malformed_webhook(self):
        cfg = test_cfg()
        result = validate_webhook_payload({"event": "SIGNAL_LONG"}, cfg)
        self.assertFalse(result.ok)
        self.assertEqual(result.reason, WebhookReason.WEBHOOK_INVALID)

    def test_t06_market_data_stale(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            assert bar is not None
            runner.provider._sim_now = bar.timestamp + timedelta(seconds=120)
            runner.provider._staleness_limit = 60
            health = runner.provider.health()
            self.assertEqual(health.state, DataHealth.DATA_STALE)

    def test_t07_market_data_gap(self):
        cache = BarCache()
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        cache.append(Bar(t0, 1, 2, 0.5, 1.5))
        cache.append(Bar(t0 + timedelta(minutes=5), 1.5, 2.5, 1.0, 2.0))
        self.assertGreater(cache.gap_bars, 0)

    def test_t08_position_conflict(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            runner.inject_signal(sig)
            runner.engine.book.internal.side = "LONG"
            sig2 = make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            r = runner.inject_signal(sig2)
            self.assertEqual(r.get("action"), TraderAction.OPPOSITE_SIGNAL_RECEIVED.value)

    def test_t09_long_target(self):
        cfg = test_cfg()
        mgmt = build_management("LONG", 20000.0, 10.0, cfg, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, mgmt.target_price + 1, 19999, mgmt.target_price)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertIsNotNone(ex)
        self.assertEqual(ex.action, TraderAction.EXIT_PROFIT)

    def test_t10_short_target(self):
        cfg = test_cfg()
        mgmt = build_management("SHORT", 20000.0, 10.0, cfg, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, 20001, mgmt.target_price - 1, mgmt.target_price)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertIsNotNone(ex)
        self.assertEqual(ex.action, TraderAction.EXIT_PROFIT)

    def test_t11_long_stop(self):
        cfg = test_cfg()
        mgmt = build_management("LONG", 20000.0, 10.0, cfg, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, 20001, mgmt.stop_price - 1, mgmt.stop_price)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertIsNotNone(ex)
        self.assertEqual(ex.action, TraderAction.EXIT_STOP)

    def test_t12_short_stop(self):
        cfg = test_cfg()
        mgmt = build_management("SHORT", 20000.0, 10.0, cfg, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, mgmt.stop_price + 1, 19999, mgmt.stop_price)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertIsNotNone(ex)
        self.assertEqual(ex.action, TraderAction.EXIT_STOP)

    def test_t13_60m_timeout(self):
        cfg = test_cfg()
        et = datetime.now(timezone.utc) - timedelta(minutes=61)
        mgmt = build_management("LONG", 20000.0, 10.0, cfg, et)
        bar = Bar(datetime.now(timezone.utc), 20000, 20005, 19995, 20001)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertIsNotNone(ex)
        self.assertEqual(ex.action, TraderAction.EXIT_TIME)

    def test_t14_same_bar_stop_first(self):
        cfg = test_cfg()
        mgmt = build_management("LONG", 20000.0, 10.0, cfg, datetime.now(timezone.utc))
        bar = Bar(datetime.now(timezone.utc), 20000, mgmt.target_price + 1, mgmt.stop_price - 1, 20000)
        ex = evaluate_exit(mgmt, bar, cfg, datetime.now(timezone.utc))
        self.assertEqual(ex.action, TraderAction.EXIT_STOP)
        self.assertIn("STOP_FIRST", ex.reason)

    def test_t15_same_direction_while_active(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            runner.inject_signal(sig)
            r = runner.inject_signal(sig)
            self.assertEqual(r.get("action"), TraderAction.SAME_DIRECTION_SIGNAL.value)

    def test_t16_opposite_signal_while_active(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            runner.inject_signal(make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close))
            r = runner.inject_signal(make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close))
            self.assertEqual(runner.engine.state, TraderState.REVERSAL_WATCH_SHORT)

    def test_t17_duplicate_order_prevention(self):
        router = SimOrderRouter()
        o1 = Order.new("MARKET_BUY", OrderSide.BUY, 1, "NQ")
        o2 = Order.new("MARKET_BUY", OrderSide.BUY, 1, "NQ")
        o2.order_id = o1.order_id
        router.submit(o1, 20000)
        o2_res, fill = router.submit(o2, 20000)
        self.assertIsNone(fill)
        self.assertEqual(o2_res.state.value, "REJECTED")

    def test_t18_simulated_order_rejection(self):
        runner, td = temp_runner()
        with td:
            runner.router.arm_reject_next()
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            r = runner.inject_signal(sig)
            self.assertFalse(r["ok"])

    def test_t19_restart_while_flat(self):
        runner, td = temp_runner()
        with td:
            runner.persist = runner.engine.persist
            runner.engine.persist()
            runner2, _ = temp_runner()
            runner2.cfg.raw["logging"]["log_dir"] = runner.cfg.log_dir
            runner2.cfg.raw["persistence"]["state_file"] = runner.cfg.state_file
            runner2.engine.persistence.path = runner.engine.persistence.path
            runner2.engine._restore()
            self.assertEqual(runner2.engine.state, TraderState.FLAT)

    def test_t20_restart_while_position_active(self):
        runner, td = temp_runner()
        with td:
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_LONG", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            runner.inject_signal(sig)
            runner.engine.persist()
            state_path = runner.engine.persistence.path
            cfg2 = test_cfg(
                **{
                    "logging.log_dir": str(runner.cfg.log_dir),
                    "persistence.state_file": str(state_path),
                }
            )
            r2 = ReplayRunner(cfg=cfg2, df=runner.df, log_dir=runner.cfg.log_dir)
            self.assertEqual(r2.engine.state, TraderState.LONG_ACTIVE)

    def test_t21_position_mismatch(self):
        book = PositionBook()
        book.internal = PositionSnapshot(side="LONG", quantity=1)
        book.broker = PositionSnapshot(side="FLAT", quantity=0)
        self.assertEqual(reconcile(book), TraderAction.POSITION_MISMATCH)

    def test_t22_data_reconnect_healthy(self):
        runner, td = temp_runner()
        with td:
            runner.run_bars(5)
            self.assertEqual(runner.provider.health().state, DataHealth.DATA_HEALTHY)

    def test_t23_duplicate_bar(self):
        cache = BarCache()
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        b = Bar(t0, 1, 2, 0.5, 1.5)
        cache.append(b)
        cache.append(b)
        self.assertEqual(cache.duplicate_bars, 1)

    def test_t24_out_of_order_bar(self):
        cache = BarCache()
        t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        cache.append(Bar(t0, 1, 2, 0.5, 1.5))
        cache.append(Bar(t0 - timedelta(minutes=1), 1, 2, 0.5, 1.5))
        self.assertEqual(cache.out_of_order_bars, 1)

    def test_pine_hash_mismatch(self):
        cfg = test_cfg()
        payload = make_test_signal("SIGNAL_LONG").to_dict()
        payload["pine_hash"] = "bad"
        result = validate_webhook_payload(payload, cfg)
        self.assertEqual(result.reason, WebhookReason.SIGNAL_HASH_MISMATCH)

    def test_same_engine_replay_and_webhook(self):
        runner, td = temp_runner()
        with td:
            engine = runner.engine
            self.assertIsInstance(engine.router, SimOrderRouter)
            bar = runner.provider.latest_bar()
            sig = make_test_signal("SIGNAL_SHORT", signal_bar_time_utc=bar.timestamp, signal_time_utc=bar.timestamp, signal_price=bar.close)
            engine.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID)
            self.assertEqual(engine.state, TraderState.SHORT_ACTIVE)


if __name__ == "__main__":
    unittest.main()
