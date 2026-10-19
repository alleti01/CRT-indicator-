"""Higher-timeframe structure bias for CDX signals."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from phase73.market_data.bar import Bar
from phase74.quality.htf_bias import (
    BEARISH,
    BULLISH,
    NEUTRAL,
    HtfBiasConfig,
    evaluate_htf_bias,
    resample,
    structure_bias,
)

T0 = datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc)


def _minute_bars(path: list[float], minutes_per_leg: int) -> list[Bar]:
    """Walk price linearly between the points in `path`, one bar per minute."""
    bars: list[Bar] = []
    i = 0
    for a, b in zip(path, path[1:]):
        for k in range(minutes_per_leg):
            o = a + (b - a) * k / minutes_per_leg
            c = a + (b - a) * (k + 1) / minutes_per_leg
            bars.append(Bar(T0 + timedelta(minutes=i), o, max(o, c) + 0.25, min(o, c) - 0.25, c, 1.0))
            i += 1
    return bars


UP = [100, 120, 110, 130, 120, 140, 130, 150, 140, 145]
DOWN = [200 - p for p in UP]
RANGE = [100, 120, 100, 120, 100, 120, 100, 120, 100, 110]


class ResampleTests(unittest.TestCase):
    def test_groups_closed_buckets_and_drops_forming_one(self) -> None:
        bars = [Bar(T0 + timedelta(minutes=i), i, i + 1, i - 1, i + 0.5) for i in range(37)]
        out = resample(bars, 15)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].open, 0)
        self.assertEqual(out[0].close, 14.5)
        self.assertEqual(out[0].high, 15)
        self.assertEqual(out[1].low, 14)

    def test_keeps_bucket_once_its_last_minute_arrives(self) -> None:
        bars = [Bar(T0 + timedelta(minutes=i), 1, 2, 0, 1) for i in range(30)]
        self.assertEqual(len(resample(bars, 15)), 2)


class StructureTests(unittest.TestCase):
    def test_higher_highs_and_lows_are_bullish(self) -> None:
        self.assertEqual(structure_bias(resample(_minute_bars(UP, 45), 15)), BULLISH)

    def test_lower_highs_and_lows_are_bearish(self) -> None:
        self.assertEqual(structure_bias(resample(_minute_bars(DOWN, 45), 15)), BEARISH)

    def test_equal_swings_are_neutral(self) -> None:
        self.assertEqual(structure_bias(resample(_minute_bars(RANGE, 45), 15)), NEUTRAL)

    def test_too_little_history_is_neutral(self) -> None:
        self.assertEqual(structure_bias(resample(_minute_bars([100, 110], 30), 15)), NEUTRAL)

    def test_close_through_last_swing_low_turns_bearish(self) -> None:
        self.assertEqual(structure_bias(resample(_minute_bars(UP + [100], 45), 15)), BEARISH)


class DecisionTests(unittest.TestCase):
    cfg = HtfBiasConfig(enabled=True, timeframes_minutes=(15, 60))

    def test_short_skipped_when_15m_and_1h_bullish(self) -> None:
        dec = evaluate_htf_bias(_minute_bars(UP, 180), "SHORT", self.cfg)
        self.assertEqual(dec.biases, {"15m": BULLISH, "1H": BULLISH})
        self.assertEqual(dec.decision, "SKIP")
        self.assertEqual(dec.reason, "HTF_ALL_BULLISH")

    def test_long_taken_with_bullish_structure(self) -> None:
        self.assertEqual(evaluate_htf_bias(_minute_bars(UP, 180), "LONG", self.cfg).decision, "TAKE")

    def test_long_skipped_when_all_bearish(self) -> None:
        self.assertEqual(evaluate_htf_bias(_minute_bars(DOWN, 180), "LONG", self.cfg).decision, "SKIP")

    def test_mixed_timeframes_take_the_signal(self) -> None:
        # 1H range, 15m breaking down at the end: only one timeframe is against the long.
        bars = _minute_bars(RANGE, 180)
        tail = _minute_bars([110, 104, 108, 98, 102, 92], 30)
        start = bars[-1].timestamp + timedelta(minutes=1)
        bars += [Bar(start + (b.timestamp - T0), b.open, b.high, b.low, b.close) for b in tail]
        dec = evaluate_htf_bias(bars, "LONG", self.cfg)
        self.assertEqual(dec.biases["15m"], BEARISH)
        self.assertNotEqual(dec.biases["1H"], BEARISH)
        self.assertEqual(dec.decision, "TAKE")

    def test_empty_history_never_skips(self) -> None:
        self.assertEqual(evaluate_htf_bias([], "SHORT", self.cfg).decision, "TAKE")


if __name__ == "__main__":
    unittest.main()
