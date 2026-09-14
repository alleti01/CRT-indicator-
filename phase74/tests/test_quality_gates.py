"""Unit tests for Phase74 quality gates, day halt, and trail overlay."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction
from phase73.trader.management import ManagementState, build_management
from phase73.config.loader import Phase73Config
from phase74.quality.day_halt import PropDayHalt
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
        bars = []
        for i in range(20):
            close = 100.0 if i == 19 else 120.0
            bars.append(_bar(i, 120.0, 140.0, 100.0, close))
        d = evaluate_quality_gates(bars, "SHORT", atr=10.0, cfg=self.cfg)
        self.assertEqual(d.reason, "SKIP_FALSE_BREAK")

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

    def test_no_flatten_at_2_5r_locks_stop(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig())
        mgmt = self._mgmt()
        bar = _bar(1, 110.0, 126.0, 123.0, 124.0)
        dec = overlay.on_bar(mgmt, bar)
        self.assertIsNone(dec)
        self.assertTrue(overlay.banked)
        self.assertAlmostEqual(mgmt.stop_price, 120.0)

    def test_same_bar_2_5_then_through_lock_exits_plus_2r(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig())
        mgmt = self._mgmt()
        bar = _bar(1, 110.0, 126.0, 119.0, 119.5)
        dec = overlay.on_bar(mgmt, bar)
        self.assertIsNotNone(dec)
        assert dec is not None
        self.assertEqual(dec.reason, "TRAIL_STOP")
        self.assertAlmostEqual(dec.exit_price, 120.0)
        self.assertEqual(dec.action, TraderAction.EXIT_PROFIT)

    def test_trail_ratchets_then_exits(self) -> None:
        overlay = TrailOverlay(TrailOverlayConfig())
        mgmt = self._mgmt()
        overlay.on_bar(mgmt, _bar(1, 110.0, 126.0, 123.0, 124.0))
        self.assertAlmostEqual(mgmt.stop_price, 120.0)
        dec = overlay.on_bar(mgmt, _bar(2, 124.0, 140.0, 132.0, 138.0))
        self.assertIsNone(dec)
        self.assertAlmostEqual(mgmt.stop_price, 130.0)
        dec = overlay.on_bar(mgmt, _bar(3, 138.0, 139.0, 129.0, 130.0))
        self.assertIsNotNone(dec)
        assert dec is not None
        self.assertEqual(dec.reason, "TRAIL_STOP")
        self.assertAlmostEqual(dec.exit_price, 130.0)


if __name__ == "__main__":
    unittest.main()
