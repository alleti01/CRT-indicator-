"""One attempt per trade range — skip while close is still inside."""
from __future__ import annotations

import copy
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from phase73.replay.runner import _synthetic_bars
from phase73.webhook.schemas import WebhookReason, make_test_signal
from phase74.config.loader import Phase74Config, load_phase74_config
from phase74.latency.tracker import LatencyTracker
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.quality.range_lock import (
    SKIP_RANGE_LOCK,
    RangeLock,
    RangeLockConfig,
    seed_from_paper_trades,
    trade_excursion,
)
from phase74.runtime.live_stack import LiveStack

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def _rth(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 21, hour, minute, tzinfo=ET)


class TradeExcursionTests(unittest.TestCase):
    def test_long_uses_mfe_mae_and_exit(self) -> None:
        hi, lo = trade_excursion("LONG", fill=100.0, exit_px=99.0, mfe_r=0.5, mae_r=1.0, atr=10.0)
        self.assertEqual(hi, 105.0)
        self.assertEqual(lo, 90.0)

    def test_short_uses_mfe_mae_and_exit(self) -> None:
        hi, lo = trade_excursion("SHORT", fill=100.0, exit_px=101.0, mfe_r=2.0, mae_r=1.0, atr=10.0)
        self.assertEqual(hi, 110.0)
        self.assertEqual(lo, 80.0)


class RangeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lock = RangeLock(RangeLockConfig(enabled=True), path=None)

    def test_no_lock_allows(self) -> None:
        self.assertEqual(self.lock.evaluate(100.0, _rth(12)), "")

    def test_inside_close_skips_both_sides(self) -> None:
        self.lock.arm(110.0, 90.0, _rth(12, 30))
        self.assertEqual(self.lock.evaluate(100.0, _rth(12, 45)), SKIP_RANGE_LOCK)
        self.assertTrue(self.lock.active)

    def test_close_through_high_releases(self) -> None:
        self.lock.arm(110.0, 90.0, _rth(12, 30))
        self.assertEqual(self.lock.evaluate(110.25, _rth(13)), "")
        self.assertFalse(self.lock.active)

    def test_close_through_low_releases(self) -> None:
        self.lock.arm(110.0, 90.0, _rth(12, 30))
        self.assertEqual(self.lock.evaluate(89.75, _rth(13)), "")
        self.assertFalse(self.lock.active)

    def test_close_on_edge_stays_locked(self) -> None:
        self.lock.arm(110.0, 90.0, _rth(12, 30))
        self.assertEqual(self.lock.evaluate(110.0, _rth(13)), SKIP_RANGE_LOCK)
        self.assertEqual(self.lock.evaluate(90.0, _rth(13, 1)), SKIP_RANGE_LOCK)

    def test_session_roll_clears(self) -> None:
        self.lock.arm(110.0, 90.0, _rth(15, 0))
        self.assertEqual(self.lock.evaluate(100.0, _rth(16, 5)), "")
        self.assertFalse(self.lock.active)

    def test_disabled_never_skips(self) -> None:
        lock = RangeLock(RangeLockConfig(enabled=False), path=None)
        lock.arm(110.0, 90.0, _rth(12))
        self.assertEqual(lock.evaluate(100.0, _rth(12, 30)), "")

    def test_persist_reload_keeps_lock(self) -> None:
        path = Path(tempfile.mkdtemp()) / "range_lock.json"
        first = RangeLock(RangeLockConfig(enabled=True), path=path)
        first.arm(110.0, 90.0, _rth(12, 30))
        second = RangeLock(RangeLockConfig(enabled=True), path=path)
        self.assertTrue(second.active)
        self.assertEqual(second.evaluate(100.0, _rth(13)), SKIP_RANGE_LOCK)

    def test_seed_from_last_journal_row(self) -> None:
        td = Path(tempfile.mkdtemp())
        csv_path = td / "paper_trades.csv"
        csv_path.write_text(
            "direction,fill_price,exit_price,exit_timestamp,MFE,MAE,atr\n"
            "LONG,100.0,99.0,2026-09-21T16:30:00+00:00,0.5,1.0,10.0\n",
            encoding="utf-8",
        )
        lock = RangeLock(RangeLockConfig(enabled=True), path=None)
        self.assertTrue(seed_from_paper_trades(lock, csv_path))
        self.assertTrue(lock.active)
        self.assertEqual(lock.evaluate(100.0, _rth(13)), SKIP_RANGE_LOCK)


def _stack_cfg(**extra) -> Phase74Config:
    raw = copy.deepcopy(load_phase74_config().raw)
    raw.setdefault("mode", {}).update(
        {"shadow_mode": False, "paper_mode": True, "trading_enabled": True}
    )
    raw.setdefault("contracts", {})["contract_month"] = "202609"
    raw.setdefault("logging", {})["log_dir"] = tempfile.mkdtemp()
    raw.setdefault("persistence", {})["state_file"] = str(Path(raw["logging"]["log_dir"]) / "state.json")
    raw["persistence"]["idempotency_file"] = str(Path(raw["logging"]["log_dir"]) / "idempotency.jsonl")
    raw.setdefault("quality_gates", {})["enabled"] = False
    raw["quality_gates"]["allow_globex_entries"] = True
    raw.setdefault("trail_overlay", {})["enabled"] = False
    raw.setdefault("range_lock", {})["enabled"] = False
    raw["range_lock"].update(extra)
    return Phase74Config(raw=raw)


class RangeLockStackTests(unittest.TestCase):
    def test_webhook_skipped_while_close_inside_spent_range(self) -> None:
        cfg = _stack_cfg(enabled=True)
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        stack = LiveStack(cfg, md)
        bar = md.latest_bar()
        stack.range_lock.arm(bar.close + 20.0, bar.close - 20.0, bar.timestamp)
        sig = make_test_signal(
            "SIGNAL_SHORT",
            signal_bar_time_utc=bar.timestamp,
            signal_time_utc=bar.timestamp,
            signal_price=bar.close,
        )
        result = stack.on_webhook_signal(sig, WebhookReason.WEBHOOK_VALID, LatencyTracker())
        self.assertFalse(result.get("ok"))
        self.assertEqual(result.get("reason"), SKIP_RANGE_LOCK)
