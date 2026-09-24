"""Unit tests for Phase74 quality gates, day halt, and trail overlay."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction
from phase73.trader.management import ManagementState, build_management
from phase73.config.loader import Phase73Config
from phase74.config.loader import load_phase74_config
from phase74.quality.day_halt import (
    PropDayHalt,
    new_entries_blocked_session,
    seed_day_halt_from_paper_trades,
)
from phase74.quality.gates import QualityGateConfig, evaluate_quality_gates
from phase74.quality.trail import TrailOverlay, TrailOverlayConfig


def _ts(i: int) -> datetime:
    return datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc) + timedelta(minutes=i)


def _bar(i: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(_ts(i), o, h, l, c, 10.0)


def _flat_box(n: int = 20, lo: float = 100.0, hi: float = 105.0, close: float = 102.0) -> list[Bar]:
    mid = (lo + hi) / 2
    return [_bar(i, mid, hi, lo, close) for i in range(n)]


class QualityGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = QualityGateConfig()

    def test_skip_data_too_few_bars(self) -> None:
        d = evaluate_quality_gates(_flat_box(5), "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_DATA")
        self.assertEqual(d.decision, "SKIP")

    def test_skip_data_missing_atr(self) -> None:
        d = evaluate_quality_gates(_flat_box(20), "LONG", atr=0.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_DATA")

    def test_skip_chop_tight_box(self) -> None:
        bars = _flat_box(20, lo=100.0, hi=105.0, close=102.0)
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_CHOP")

    def test_skip_false_break_short_at_range_low(self) -> None:
        bars = [_bar(i, 120.0, 140.0, 100.0, 120.0) for i in range(19)]
        bars.append(_bar(19, 120.0, 140.0, 100.0, 106.0))
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")

    def _prior_range_then(self, last_o: float, last_h: float, last_l: float, last_c: float) -> list[Bar]:
        bars = [_bar(i, 100.0, 110.0, 90.0, 100.0) for i in range(19)]
        bars.append(_bar(19, last_o, last_h, last_l, last_c))
        return bars

    def test_take_long_close_through_prior_high(self) -> None:
        bars = self._prior_range_then(100.0, 111.5, 99.0, 111.0)
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.decision, "TAKE")
        self.assertEqual(d.reason, "TAKE")

    def test_take_short_close_through_prior_low(self) -> None:
        bars = self._prior_range_then(100.0, 101.0, 88.5, 89.0)
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.decision, "TAKE")
        self.assertEqual(d.reason, "TAKE")

    def test_skip_long_near_high_not_through_prior(self) -> None:
        bars = self._prior_range_then(100.0, 110.0, 100.0, 109.0)
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")

    def test_close_through_bypasses_late_move(self) -> None:
        bars = self._prior_range_then(100.0, 114.0, 99.0, 112.0)
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertGreater(d.progress_atr, 1.0)
        self.assertEqual(d.decision, "TAKE")

    def test_skip_no_trend_mid_box(self) -> None:
        bars = self._prior_range_then(100.0, 104.0, 98.0, 102.0)
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertLess(abs(d.progress_atr), 0.5)
        self.assertEqual(d.reason, "SKIP_NO_TREND")

    def test_skip_no_trend_short_flat_progress(self) -> None:
        bars = self._prior_range_then(100.0, 103.0, 97.0, 99.0)
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertLess(abs(d.progress_atr), 0.5)
        self.assertEqual(d.reason, "SKIP_NO_TREND")

    def test_take_at_exactly_half_atr_progress(self) -> None:
        bars = self._prior_range_then(100.0, 108.0, 99.0, 105.0)
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertAlmostEqual(d.progress_atr, 0.5)
        self.assertEqual(d.decision, "TAKE")

    def test_close_through_bypasses_no_trend(self) -> None:
        bars = [_bar(i, 109.0, 110.0, 90.0, 109.0) for i in range(19)]
        bars.append(_bar(19, 109.0, 112.0, 108.0, 110.5))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertLess(abs(d.progress_atr), 0.5)
        self.assertEqual(d.decision, "TAKE")

    def test_skip_chop_even_if_close_through(self) -> None:
        bars = [_bar(i, 102.0, 105.0, 100.0, 102.0) for i in range(19)]
        bars.append(_bar(19, 102.0, 106.0, 101.0, 105.5))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_CHOP")

    def test_skip_atr_cap_even_if_close_through(self) -> None:
        bars = [_bar(i, 100.0, 140.0, 90.0, 100.0) for i in range(19)]
        bars.append(_bar(19, 100.0, 142.0, 99.0, 141.0))
        d = evaluate_quality_gates(bars, "LONG", atr=16.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_ATR_CAP")

    def test_skip_late_move_long_already_ran(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * (12.0 / 19.0)
            bars.append(_bar(i, c, 125.0, 100.0, c))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_LATE_MOVE")
        self.assertGreater(d.progress_atr, 1.0)

    def test_take_expansion_away_from_edge(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * (8.0 / 19.0)
            bars.append(_bar(i, c, 130.0, 100.0, c))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.decision, "TAKE")
        self.assertEqual(d.reason, "TAKE")

    def test_skip_atr_cap_above_15(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * (8.0 / 19.0)
            bars.append(_bar(i, c, 140.0, 100.0, c))
        d = evaluate_quality_gates(bars, "LONG", atr=16.0, cfg=self.cfg)
        self.assertEqual(d.decision, "SKIP")
        self.assertEqual(d.reason, "SKIP_ATR_CAP")

    def test_take_at_atr_cap_exactly_15(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * (8.0 / 19.0)
            bars.append(_bar(i, c, 130.0, 100.0, c))
        d = evaluate_quality_gates(bars, "LONG", atr=15.0, cfg=self.cfg)
        self.assertEqual(d.decision, "TAKE")
        self.assertEqual(d.reason, "TAKE")

    def test_take_atr_17_when_cap_is_18(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * (12.0 / 19.0)
            bars.append(_bar(i, c, 160.0, 100.0, c))
        cfg = QualityGateConfig(max_atr_points=18.0)
        d = evaluate_quality_gates(bars, "LONG", atr=17.3, cfg=cfg)
        self.assertEqual(d.decision, "TAKE")

    def test_take_continuation_short_three_of_four_bearish_at_lows(self) -> None:
        """9:34 shape: dump then small green pause at the 20-bar low still TAKEs."""
        bars = [_bar(i, 130.0, 140.0, 120.0, 130.0) for i in range(16)]
        bars.append(_bar(16, 128.0, 129.0, 118.0, 119.0))
        bars.append(_bar(17, 119.0, 120.0, 110.0, 111.0))
        bars.append(_bar(18, 111.0, 112.0, 102.0, 103.0))
        bars.append(_bar(19, 103.0, 106.0, 100.0, 104.0))
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertGreater(d.progress_atr, 1.0)
        self.assertLessEqual(d.percentile_in_box, 0.15)
        self.assertEqual(d.decision, "TAKE")
        self.assertEqual(d.reason, "TAKE")

    def test_skip_spike_long_two_of_four_bullish_at_highs(self) -> None:
        """3:32 shape: mixed candles then one spike into the 20-bar high still SKIPs."""
        bars = [_bar(i, 110.0, 120.0, 100.0, 110.0) for i in range(16)]
        bars.append(_bar(16, 110.0, 111.0, 108.0, 109.0))
        bars.append(_bar(17, 109.0, 112.0, 108.0, 111.0))
        bars.append(_bar(18, 111.0, 112.0, 109.0, 110.0))
        bars.append(_bar(19, 110.0, 120.0, 109.5, 119.0))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.decision, "SKIP")
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")

    def test_two_bearish_bodies_do_not_bypass_false_break(self) -> None:
        bars = [_bar(i, 120.0, 140.0, 100.0, 120.0) for i in range(18)]
        bars.append(_bar(18, 120.0, 121.0, 110.0, 111.0))
        bars.append(_bar(19, 111.0, 112.0, 100.0, 106.0))
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")

    def test_long_close_equal_prior_high_is_not_through(self) -> None:
        bars = [_bar(i, 100.0, 110.0, 90.0, 100.0) for i in range(19)]
        bars.append(_bar(19, 108.0, 110.0, 107.0, 110.0))
        d = evaluate_quality_gates(bars, "LONG", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.decision, "SKIP")
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")


class PropDayHaltTests(unittest.TestCase):
    def test_halt_after_two_losers(self) -> None:
        h = PropDayHalt()
        h.record_closed(-1.0, dollars=-200.0)
        self.assertFalse(h.should_halt_new_entries())
        h.record_closed(-1.0, dollars=-200.0)
        self.assertTrue(h.should_halt_new_entries())
        self.assertEqual(h.reason, "HALT_DAY_LOSERS")

    def test_halt_at_minus_400_dollars(self) -> None:
        h = PropDayHalt()
        h.record_closed(-1.0, dollars=-400.0)
        self.assertTrue(h.should_halt_new_entries())
        self.assertEqual(h.reason, "HALT_DAY_DOLLARS")

    def test_halt_after_two_winners(self) -> None:
        h = PropDayHalt()
        h.record_closed(2.0, dollars=311.0)
        self.assertFalse(h.should_halt_new_entries())
        h.record_closed(2.0, dollars=300.0)
        self.assertTrue(h.should_halt_new_entries())
        self.assertEqual(h.reason, "HALT_DAY_WINS")

    def test_one_winner_halts_when_max_is_one(self) -> None:
        h = PropDayHalt(max_winners=1, big_win_dollars=10_000.0)
        now = datetime(2026, 9, 21, 14, 20, tzinfo=timezone.utc)  # 10:20 AM ET
        h.record_closed(2.1, now, dollars=665.0)
        later = datetime(2026, 9, 21, 17, 10, tzinfo=timezone.utc)  # 1:10 PM ET
        self.assertTrue(h.should_halt_new_entries(later))
        self.assertEqual(h.reason, "HALT_DAY_WINS")

    def test_live_config_is_two_winners_per_session(self) -> None:
        qg = load_phase74_config().section("quality_gates")
        self.assertEqual(int(qg["day_max_winners"]), 1)

    def test_live_config_range_lock_is_off(self) -> None:
        rl = load_phase74_config().section("range_lock")
        self.assertFalse(bool(rl.get("enabled")))

    def test_live_config_allows_globex_entries(self) -> None:
        qg = load_phase74_config().section("quality_gates")
        self.assertTrue(bool(qg.get("allow_globex_entries")))

    def test_live_config_trusts_cdx_prints(self) -> None:
        qg = load_phase74_config().section("quality_gates")
        self.assertTrue(bool(qg.get("enabled")))
        self.assertFalse(bool(qg.get("filter_signals")))
        self.assertEqual(int(qg.get("cdx_repeat_seconds", 0)), 300)

    def test_seed_journal_restores_win_halt(self) -> None:
        td = Path(tempfile.mkdtemp())
        csv_path = td / "paper_trades.csv"
        csv_path.write_text(
            "net_R,atr,exit_timestamp\n"
            "2.1,15.77,2026-09-21T14:17:00+00:00\n",
            encoding="utf-8",
        )
        h = PropDayHalt(max_winners=1, big_win_dollars=10_000.0)
        self.assertTrue(seed_day_halt_from_paper_trades(h, csv_path))
        now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
        self.assertTrue(h.should_halt_new_entries(now))
        self.assertEqual(h.reason, "HALT_DAY_WINS")
        self.assertEqual(h.winners, 1)

    def test_seed_skips_nt_rejected_signal(self) -> None:
        td = Path(tempfile.mkdtemp())
        csv_path = td / "paper_trades.csv"
        csv_path.write_text(
            "pine_signal_id,net_R,atr,exit_timestamp\n"
            "rejected-short,-1.0,5.0,2026-09-22T23:17:00+00:00\n"
            "kept-short,-1.0,5.0,2026-09-22T23:20:00+00:00\n",
            encoding="utf-8",
        )
        audit = td / "audit.jsonl"
        audit.write_text(
            '{"event":"COMMAND_REJECTED","reason":"REJECT_POSITION_OPEN","signal_id":"rejected-short"}\n',
            encoding="utf-8",
        )
        h = PropDayHalt()
        seed_day_halt_from_paper_trades(h, csv_path, audit_path=audit)
        self.assertEqual(h.losers, 1)

    def test_halt_after_one_big_win(self) -> None:
        h = PropDayHalt()
        h.record_closed(4.31, dollars=1120.0)
        self.assertTrue(h.should_halt_new_entries())
        self.assertEqual(h.reason, "HALT_DAY_BIG_WIN")

    def test_halt_giveback_from_peak(self) -> None:
        h = PropDayHalt()
        h.record_closed(2.0, dollars=450.0)
        self.assertFalse(h.should_halt_new_entries())
        h.record_closed(-1.0, dollars=-300.0)
        self.assertTrue(h.should_halt_new_entries())
        self.assertEqual(h.reason, "HALT_DAY_GIVEBACK")

    def test_winner_does_not_count_as_loser(self) -> None:
        h = PropDayHalt()
        h.record_closed(2.0, dollars=311.0)
        h.record_closed(-1.0, dollars=-99.0)
        self.assertFalse(h.should_halt_new_entries())
        self.assertEqual(h.losers, 1)
        self.assertEqual(h.winners, 1)

    def test_overnight_wins_do_not_halt_rth(self) -> None:
        h = PropDayHalt()
        globex = datetime(2026, 9, 16, 6, 0, tzinfo=timezone.utc)  # 2:00 AM ET
        h.record_closed(2.0, globex, dollars=222.0)
        h.record_closed(2.4, globex, dollars=323.0)
        self.assertTrue(h.should_halt_new_entries(globex))
        self.assertEqual(h.reason, "HALT_DAY_WINS")
        rth = datetime(2026, 9, 16, 14, 45, tzinfo=timezone.utc)  # 10:45 AM ET
        self.assertFalse(h.should_halt_new_entries(rth))
        self.assertEqual(h.winners, 0)
        self.assertEqual(h.losers, 0)

    def test_rth_wins_do_not_halt_after_hours(self) -> None:
        h = PropDayHalt()
        rth = datetime(2026, 9, 16, 15, 0, tzinfo=timezone.utc)  # 11:00 AM ET
        h.record_closed(2.0, rth, dollars=390.0)
        h.record_closed(2.0, rth, dollars=400.0)
        self.assertTrue(h.should_halt_new_entries(rth))
        evening = datetime(2026, 9, 16, 22, 10, tzinfo=timezone.utc)  # 6:10 PM ET
        self.assertFalse(h.should_halt_new_entries(evening))
        self.assertEqual(h.winners, 0)

    def test_one_globex_loss_does_not_halt_rth(self) -> None:
        h = PropDayHalt()
        globex = datetime(2026, 9, 16, 4, 51, tzinfo=timezone.utc)  # 12:51 AM ET
        h.record_closed(-1.0, globex, dollars=-119.0)
        self.assertFalse(h.should_halt_new_entries(globex))
        rth = datetime(2026, 9, 16, 13, 46, tzinfo=timezone.utc)  # 9:46 AM ET
        self.assertFalse(h.should_halt_new_entries(rth))
        self.assertEqual(h.losers, 0)


class GlobexEntryBlockTests(unittest.TestCase):
    def test_pre_rth_blocked(self) -> None:
        ts = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)  # 8:00 AM ET
        self.assertEqual(new_entries_blocked_session(ts), "SKIP_GLOBEX")

    def test_rth_allowed(self) -> None:
        ts = datetime(2026, 9, 18, 13, 30, tzinfo=timezone.utc)  # 9:30 AM ET
        self.assertEqual(new_entries_blocked_session(ts), "")

    def test_after_hours_blocked(self) -> None:
        ts = datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc)  # 4:00 PM ET
        self.assertEqual(new_entries_blocked_session(ts), "SKIP_GLOBEX")

    def test_allow_globex_opt_in(self) -> None:
        ts = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(new_entries_blocked_session(ts, allow_globex_entries=True), "")


class HoldWinnerTests(unittest.TestCase):
    def test_hour_stop_is_skipped_only_while_green(self) -> None:
        from types import SimpleNamespace

        from phase74.runtime.live_stack import _keep_winner_past_hour

        long_mgmt = SimpleNamespace(side="LONG", entry_price=100.0)
        green = SimpleNamespace(close=101.0)
        red = SimpleNamespace(close=99.0)
        self.assertTrue(_keep_winner_past_hour("MAX_HOLD_60M", long_mgmt, green))
        self.assertFalse(_keep_winner_past_hour("MAX_HOLD_60M", long_mgmt, red))
        self.assertFalse(_keep_winner_past_hour("M0_STOP", long_mgmt, green))


class TrailOverlayTests(unittest.TestCase):
    def _mgmt(self) -> ManagementState:
        cfg = Phase73Config(
            raw={
                "management": {"stop_atr": 1.0, "target_r": 2.5, "max_hold_minutes": 60},
                "execution": {"same_bar_collision": "STOP_FIRST"},
            }
        )
        et = _ts(0)
        return build_management("LONG", 100.0, 10.0, cfg, et)

    def test_profit_cap_holds_through_2r_and_exits_at_1200(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig(profit_cap_points=60.0))
        mgmt = self._mgmt()
        self.assertIsNone(overlay.on_bar(mgmt, _bar(1, 100.0, 130.0, 100.0, 125.0)))
        dec = overlay.on_bar(mgmt, _bar(2, 125.0, 160.0, 120.0, 155.0))
        self.assertIsNotNone(dec)
        assert dec is not None
        self.assertEqual(dec.reason, "PROFIT_CAP")
        self.assertAlmostEqual(dec.exit_price or 0.0, 160.0)

    def test_same_bar_2_5_then_through_lock_exits_plus_2r(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig())
        mgmt = self._mgmt()
        dec = overlay.on_bar(mgmt, _bar(1, 110.0, 126.0, 119.0, 119.5))
        self.assertIsNotNone(dec)
        assert dec is not None
        self.assertEqual(dec.reason, "TRAIL_STOP")
        self.assertAlmostEqual(dec.exit_price or 0.0, 120.0)

    def test_trail_ratchets_then_exits(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig())
        mgmt = self._mgmt()
        overlay.on_bar(mgmt, _bar(1, 110.0, 126.0, 123.0, 124.0))
        self.assertTrue(overlay.banked)
        self.assertAlmostEqual(mgmt.stop_price, 120.0)
        dec = overlay.on_bar(mgmt, _bar(2, 124.0, 140.0, 132.0, 138.0))
        self.assertIsNone(dec)
        self.assertAlmostEqual(mgmt.stop_price, 130.0)
        dec = overlay.on_bar(mgmt, _bar(3, 138.0, 139.0, 129.0, 130.0))
        self.assertIsNotNone(dec)
        assert dec is not None
        self.assertEqual(dec.reason, "TRAIL_STOP")
        self.assertAlmostEqual(dec.exit_price or 0.0, 130.0)


class CdxTrustStackTests(unittest.TestCase):
    def _stack(self, *, filter_signals: bool, repeat: int = 300):
        from phase73.replay.runner import _synthetic_bars
        from phase73.webhook.schemas import WebhookReason, make_test_signal
        from phase74.latency.tracker import LatencyTracker
        from phase74.market_data.live_provider import StreamLiveDataProvider
        from phase74.runtime.live_stack import LiveStack
        from phase74.tests.test_phase74_integration import p74_cfg

        cfg = p74_cfg()
        cfg.raw["quality_gates"]["enabled"] = True
        cfg.raw["quality_gates"]["filter_signals"] = filter_signals
        cfg.raw["quality_gates"]["cdx_repeat_seconds"] = repeat
        md = StreamLiveDataProvider(_synthetic_bars(50))
        md.connect()
        while md.advance():
            pass
        return LiveStack(cfg, md), md

    def test_filters_off_does_not_skip_for_pa(self) -> None:
        from phase73.webhook.schemas import WebhookReason, make_test_signal
        from phase74.latency.tracker import LatencyTracker
        from phase74.quality.gates import evaluate_quality_gates

        stack, md = self._stack(filter_signals=False)
        bars = list(md.recent_bars(20))
        atr = float(md.atr())
        gate = evaluate_quality_gates(bars, "LONG", atr)
        self.assertEqual(gate.decision, "SKIP")
        bar = md.latest_bar()
        now = md.current_time()
        result = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertTrue(result.get("ok"), result)

    def test_cdx_repeat_collapses_same_direction(self) -> None:
        from phase73.webhook.schemas import WebhookReason, make_test_signal
        from phase74.latency.tracker import LatencyTracker

        stack, md = self._stack(filter_signals=False, repeat=300)
        bar = md.latest_bar()
        now = md.current_time()
        first = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_id="cdx-1",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now,
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertTrue(first.get("ok"), first)
        second = stack.on_webhook_signal(
            make_test_signal(
                "SIGNAL_LONG",
                signal_id="cdx-2",
                signal_bar_time_utc=bar.timestamp,
                signal_time_utc=now + timedelta(seconds=90),
                signal_price=bar.close,
            ),
            WebhookReason.WEBHOOK_VALID,
            LatencyTracker(),
        )
        self.assertFalse(second.get("ok"))
        self.assertEqual(second.get("reason"), "SKIP_CDX_REPEAT")


if __name__ == "__main__":
    unittest.main()
