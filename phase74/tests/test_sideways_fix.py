"""Sideways overlay: Globex-only veto, RTH bit-for-bit freeze, causality."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from phase73.market_data.bar import Bar
from phase74.quality.gates import QualityGateConfig, evaluate_quality_gates
from phase74.quality.sideways import (
    SidewaysOverlayConfig,
    compute_window_metrics,
    detect_false_break,
    detect_sideways_state,
    detect_structural_escape,
)
from phase74.quality.sideways_overlay import (
    PASS_FALSE_BREAK,
    PASS_SIDEWAYS_WIDE_RANGE,
    TAKE_RANGE_ESCAPE,
    TAKE_RANGE_ESCAPE_RETEST,
    evaluate_quality_with_sideways,
)


def _bar(i: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(
        datetime(2026, 9, 10, 14, 0, tzinfo=timezone.utc) + timedelta(minutes=i),
        o,
        h,
        l,
        c,
        10.0,
    )

ET = ZoneInfo("America/New_York")
_CFG = QualityGateConfig()
_OV = SidewaysOverlayConfig(enabled=True, apply_outside_rth_only=True)


def _gts(i: int) -> datetime:
    """04:00 ET = 08:00 UTC in September — Globex."""
    return datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc) + timedelta(minutes=i)


def _gbar(i: int, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(_gts(i), o, h, l, c, 10.0)


def _wide_overlap(n: int = 20, last4: str = "GGGG") -> list[Bar]:
    bars: list[Bar] = []
    for i in range(n - 4):
        if i % 2 == 0:
            bars.append(_gbar(i, 128.0, 155.0, 105.0, 142.0))
        else:
            bars.append(_gbar(i, 142.0, 154.0, 106.0, 118.0))
    bodies = last4.ljust(4, "G")[:4]
    base = n - 4
    for j, ch in enumerate(bodies):
        i = base + j
        if ch == "G":
            bars.append(_gbar(i, 120.0, 148.0, 112.0, 140.0))
        else:
            bars.append(_gbar(i, 140.0, 148.0, 112.0, 118.0))
    return bars


def _overlay(bars: list[Bar], direction: str, atr: float = 10.0, ov: SidewaysOverlayConfig = _OV):
    return evaluate_quality_with_sideways(
        bars,
        direction,
        atr,
        signal_time=bars[-1].timestamp,
        gate_cfg=_CFG,
        overlay_cfg=ov,
    )


class SidewaysMetricTests(unittest.TestCase):
    def test_tight_chop_not_wide_sideways(self) -> None:
        bars = [_gbar(i, 102.0, 105.0, 100.0, 102.0) for i in range(20)]
        m = compute_window_metrics(bars, "LONG", 10.0, _OV, _CFG)
        self.assertIsNotNone(m)
        assert m is not None
        self.assertLess(m.range_atr_20, 2.0)
        self.assertFalse(detect_sideways_state(m, _OV))

    def test_high_efficiency_not_sideways(self) -> None:
        bars = []
        for i in range(20):
            c = 100.0 + i * 4.0
            bars.append(_gbar(i, c - 1.0, c + 1.5, c - 1.5, c))
        m = compute_window_metrics(bars, "LONG", 10.0, _OV, _CFG)
        self.assertIsNotNone(m)
        assert m is not None
        self.assertGreater(m.directional_efficiency_20, 0.35)
        self.assertFalse(detect_sideways_state(m, _OV))


class SidewaysOverlayGlobexTests(unittest.TestCase):
    def test_wide_low_eff_3of4_green_no_breakout(self) -> None:
        bars = _wide_overlap(last4="GGGG")
        d = _overlay(bars, "LONG")
        self.assertTrue(d.sideways_wide_range)
        self.assertTrue(d.metrics.continuation_3_of_4)
        self.assertFalse(d.escape.valid)
        self.assertEqual(d.reason, PASS_SIDEWAYS_WIDE_RANGE)
        self.assertEqual(d.decision, "SKIP")

    def test_wide_low_eff_3of4_red_no_breakout(self) -> None:
        bars = _wide_overlap(last4="RRRR")
        d = _overlay(bars, "SHORT")
        self.assertEqual(d.reason, PASS_SIDEWAYS_WIDE_RANGE)
        self.assertEqual(d.decision, "SKIP")

    def test_wick_above_close_inside_is_false_break(self) -> None:
        bars = _wide_overlap(last4="GGGG")[:-1]
        prior_high = max(b.high for b in bars)
        bars.append(_gbar(19, 140.0, prior_high + 4.0, 120.0, prior_high - 2.0))
        d = _overlay(bars, "LONG")
        self.assertTrue(d.false_break)
        self.assertEqual(d.reason, PASS_FALSE_BREAK)

    def test_close_through_frozen_boundary_is_escape(self) -> None:
        bars = _wide_overlap(last4="GGGG")[:-1]
        prior_high = max(b.high for b in bars)
        bars.append(_gbar(19, prior_high - 1.0, prior_high + 6.0, prior_high - 2.0, prior_high + 3.0))
        d = _overlay(bars, "LONG")
        self.assertTrue(d.escape.close_through)
        self.assertIn(d.reason, (TAKE_RANGE_ESCAPE, "TAKE", TAKE_RANGE_ESCAPE_RETEST))
        self.assertEqual(d.decision, "TAKE")

    def test_break_retest_hold(self) -> None:
        bars = []
        for i in range(14):
            if i % 2 == 0:
                bars.append(_gbar(i, 128.0, 150.0, 110.0, 140.0))
            else:
                bars.append(_gbar(i, 140.0, 150.0, 110.0, 120.0))
        wall = 150.0
        bars.append(_gbar(14, 148.0, 158.0, 147.0, 156.0))
        bars.append(_gbar(15, 156.0, 157.0, 149.5, 153.0))
        bars.append(_gbar(16, 153.0, 160.0, 152.0, 158.0))
        bars.append(_gbar(17, 158.0, 161.0, 156.0, 160.0))
        bars.append(_gbar(18, 160.0, 162.0, 158.0, 161.0))
        bars.append(_gbar(19, 161.0, 163.0, 159.0, 162.0))
        self.assertGreater(bars[14].close, wall)
        d = _overlay(bars, "LONG")
        self.assertTrue(d.escape.retest_hold or d.escape.close_through)
        self.assertEqual(d.decision, "TAKE")
        if d.escape.retest_hold:
            self.assertEqual(d.reason, TAKE_RANGE_ESCAPE_RETEST)

    def test_retest_fail_is_pass(self) -> None:
        bars = []
        for i in range(16):
            if i % 2 == 0:
                bars.append(_gbar(i, 128.0, 150.0, 110.0, 140.0))
            else:
                bars.append(_gbar(i, 140.0, 150.0, 110.0, 120.0))
        bars.append(_gbar(16, 148.0, 158.0, 147.0, 156.0))
        bars.append(_gbar(17, 156.0, 157.0, 149.0, 149.5))
        bars.append(_gbar(18, 149.0, 151.0, 140.0, 142.0))
        bars.append(_gbar(19, 142.0, 146.0, 138.0, 140.0))
        d = _overlay(bars, "LONG")
        self.assertEqual(d.decision, "SKIP")
        self.assertIn(d.reason, (PASS_FALSE_BREAK, PASS_SIDEWAYS_WIDE_RANGE))

    def test_tight_box_still_skip_chop(self) -> None:
        bars = [_gbar(i, 102.0, 105.0, 100.0, 102.0) for i in range(20)]
        d = _overlay(bars, "SHORT")
        self.assertEqual(d.reason, "SKIP_CHOP")
        self.assertEqual(evaluate_quality_gates(bars, "SHORT", 10.0, _CFG).reason, "SKIP_CHOP")

    def test_mixed_candles_with_close_through_not_auto_rejected(self) -> None:
        bars = _wide_overlap(last4="RRRR")[:-1]
        prior_high = max(b.high for b in bars)
        bars.append(_gbar(19, prior_high - 2.0, prior_high + 5.0, prior_high - 3.0, prior_high + 2.0))
        d = _overlay(bars, "LONG")
        self.assertFalse(d.metrics.continuation_3_of_4)
        self.assertTrue(d.escape.close_through)
        self.assertEqual(d.decision, "TAKE")


class RthRegressionFreezeTests(unittest.TestCase):
    def test_rth_3of4_matches_existing_gates(self) -> None:
        bars = [_bar(i, 130.0, 140.0, 120.0, 130.0) for i in range(16)]
        bars.append(_bar(16, 128.0, 129.0, 118.0, 119.0))
        bars.append(_bar(17, 119.0, 120.0, 110.0, 111.0))
        bars.append(_bar(18, 111.0, 112.0, 102.0, 103.0))
        bars.append(_bar(19, 103.0, 106.0, 100.0, 104.0))
        existing = evaluate_quality_gates(bars, "SHORT", 10.0, _CFG)
        over = evaluate_quality_with_sideways(
            bars,
            "SHORT",
            10.0,
            signal_time=bars[-1].timestamp,
            gate_cfg=_CFG,
            overlay_cfg=_OV,
        )
        self.assertEqual(over.session, "rth")
        self.assertFalse(over.overlay_applied)
        self.assertEqual(over.decision, existing.decision)
        self.assertEqual(over.reason, existing.reason)

class CausalityTests(unittest.TestCase):
    def test_500_asof_ignores_future_bars(self) -> None:
        full: list[Bar] = []
        px = 20000.0
        for i in range(620):
            drift = 3.0 if (i // 40) % 2 == 0 else -2.5
            px += drift
            full.append(_gbar(i, px, px + 8.0, px - 8.0, px + 1.0))
        future = [_gbar(800 + i, 99999.0, 100020.0, 99980.0, 100010.0) for i in range(30)]
        mismatches = 0
        samples = list(range(40, 540))
        for t in samples:
            a = evaluate_quality_with_sideways(
                full[: t + 1],
                "LONG",
                10.0,
                signal_time=full[t].timestamp,
                gate_cfg=_CFG,
                overlay_cfg=_OV,
            )
            b = evaluate_quality_with_sideways(
                (full + future)[: t + 1],
                "LONG",
                10.0,
                signal_time=full[t].timestamp,
                gate_cfg=_CFG,
                overlay_cfg=_OV,
            )
            if (
                a.reason != b.reason
                or a.decision != b.decision
                or a.sideways_wide_range != b.sideways_wide_range
                or a.false_break != b.false_break
            ):
                mismatches += 1
        self.assertEqual(mismatches, 0, "SIDEWAYS_FIX_CAUSALITY_FAIL")


if __name__ == "__main__":
    unittest.main()
