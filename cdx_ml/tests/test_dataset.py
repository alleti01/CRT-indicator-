"""CDX learning dataset: no look-ahead in features, correct triple-barrier labels."""
from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

from phase73.market_data.bar import Bar
from cdx_ml.dataset import (
    STOP_KINDS,
    TARGETS,
    _data_hole,
    is_alert_id,
    pullback_entry,
    build,
    features,
    stop_distances,
    triple_barrier,
)

T0 = datetime(2026, 9, 23, 13, 0, tzinfo=timezone.utc)


def _bars(n: int, start: datetime = T0, base: float = 30000.0) -> list[Bar]:
    out = []
    for i in range(n):
        c = base + 20 * math.sin(i / 37) + 5 * math.sin(i / 5)
        o = base + 20 * math.sin((i - 1) / 37) + 5 * math.sin((i - 1) / 5)
        out.append(Bar(start + timedelta(minutes=i), o, max(o, c) + 1, min(o, c) - 1, c, 10))
    return out


class LookAheadTests(unittest.TestCase):
    def test_future_bars_do_not_change_features(self) -> None:
        bars = _bars(1500)
        sig = {"signal_id": "x", "t": bars[1000].timestamp, "side": "LONG", "price": bars[999].close, "source": "cdx"}
        a, _ = build(bars, [sig], {})
        moved = bars[:1001] + [Bar(b.timestamp, b.open + 500, b.high + 500, b.low + 500, b.close + 500) for b in bars[1001:]]
        b, _ = build(moved, [sig], {})
        feat_keys = [k for k in a[0] if not k.startswith(("r_", "exit_", "mfe", "mae"))]
        for k in feat_keys:
            va, vb = a[0][k], b[0][k]
            if isinstance(va, float) and math.isnan(va):
                self.assertTrue(math.isnan(vb), k)
            else:
                self.assertEqual(va, vb, k)
        self.assertNotEqual(a[0]["mfe_pts"], b[0]["mfe_pts"])

    def test_every_option_gets_a_label(self) -> None:
        bars = _bars(1500)
        sig = {"signal_id": "x", "t": bars[1000].timestamp, "side": "SHORT", "price": bars[999].close, "source": "cdx"}
        rows, _ = build(bars, [sig], {})
        for kind in STOP_KINDS:
            for tr in TARGETS:
                key = f"{kind}_t{tr:g}"
                if kind == "cdx":
                    self.assertTrue(math.isnan(rows[0][f"r_{key}"]))
                else:
                    self.assertIn(rows[0][f"exit_{key}"], {"TARGET", "STOP", "TIME"})

    def test_cdx_levels_become_features_and_a_stop(self) -> None:
        bars = _bars(1500)
        entry = bars[999].close
        sig = {"signal_id": "x", "t": bars[1000].timestamp, "side": "LONG", "price": entry, "source": "cdx"}
        rows, _ = build(bars, [sig], {"x": {"cdx_stop": entry - 40, "cdx_tp1": entry + 40, "cdx_tp2": entry + 80}})
        self.assertAlmostEqual(rows[0]["cdx_sl_pts"], 40)
        self.assertAlmostEqual(rows[0]["cdx_tp1_r"], 1.0)
        self.assertAlmostEqual(rows[0]["cdx_tp2_r"], 2.0)
        self.assertAlmostEqual(rows[0]["dist_cdx"], 40)


class LabelTests(unittest.TestCase):
    def _path(self, closes: list[float]) -> list[Bar]:
        return [Bar(T0 + timedelta(minutes=i), c, c, c, c) for i, c in enumerate(closes)]

    def test_target_first(self) -> None:
        o = triple_barrier("LONG", 100.0, 10.0, 2.0, self._path([101, 105, 112, 121, 80]))
        self.assertEqual(o.exit, "TARGET")
        self.assertAlmostEqual(o.r, 2.0 - 0.1)

    def test_stop_first_even_if_target_later(self) -> None:
        o = triple_barrier("SHORT", 100.0, 10.0, 2.0, self._path([101, 110, 70]))
        self.assertEqual(o.exit, "STOP")
        self.assertAlmostEqual(o.r, -1.1)

    def test_same_bar_counts_as_stop(self) -> None:
        bar = Bar(T0, 100, 125, 85, 110)
        self.assertEqual(triple_barrier("LONG", 100.0, 10.0, 2.0, [bar]).exit, "STOP")

    def test_time_exit_marks_to_last_close(self) -> None:
        o = triple_barrier("LONG", 100.0, 10.0, 2.0, self._path([101, 104, 105]))
        self.assertEqual(o.exit, "TIME")
        self.assertAlmostEqual(o.r, 0.5 - 0.1)


class PullbackTests(unittest.TestCase):
    def _path(self, bars: list[tuple[float, float, float]]) -> list[Bar]:
        return [Bar(T0 + timedelta(minutes=i + 1), c, h, l, c) for i, (h, l, c) in enumerate(bars)]

    def test_short_fills_on_the_bounce_and_measures_from_the_fill(self) -> None:
        # Short at 100, ATR 10, limit 0.5 ATR higher = 105. Bounce trades 105.25, then falls to target 105 - 30 = 75.
        path = self._path([(101, 99, 100), (105.25, 101, 104), (104, 74, 75)])
        pb = pullback_entry("SHORT", 100.0, 10.0, 0.5, 2.0, path)
        self.assertTrue(pb.filled)
        self.assertEqual(pb.fill_price, 105.0)
        self.assertEqual(pb.outcome.exit, "TARGET")
        self.assertAlmostEqual(pb.outcome.r, 2.0 - 1.0 / 15.0)

    def test_touching_the_limit_without_trading_through_is_no_fill(self) -> None:
        path = self._path([(105.0, 99, 100), (101, 90, 91)])
        self.assertFalse(pullback_entry("SHORT", 100.0, 10.0, 0.5, 2.0, path).filled)

    def test_limit_expires_after_15_minutes(self) -> None:
        path = self._path([(100.5, 99, 100)] * 15 + [(106, 99, 105)])
        self.assertFalse(pullback_entry("SHORT", 100.0, 10.0, 0.5, 2.0, path).filled)

    def test_stop_on_the_fill_bar_counts(self) -> None:
        # Long limit at 95 fills, and the same bar also drops through the 80 stop.
        path = self._path([(100, 79, 85)])
        pb = pullback_entry("LONG", 100.0, 10.0, 0.5, 2.0, path)
        self.assertTrue(pb.filled)
        self.assertEqual(pb.outcome.exit, "STOP")


class SignalIdTests(unittest.TestCase):
    def test_only_tradingview_alert_ids_count(self) -> None:
        self.assertTrue(is_alert_id("2026-10-09T12:42:00Z"))
        self.assertFalse(is_alert_id("d27035f4-30bb-4c19-9aa0-51cabf068a16"))  # readiness-probe test signal
        self.assertFalse(is_alert_id("REENTRY_abc"))


class GapTests(unittest.TestCase):
    def test_daily_break_is_not_a_hole(self) -> None:
        a = datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
        self.assertFalse(_data_hole(a, a + timedelta(minutes=61)))

    def test_overnight_hole_is_a_hole(self) -> None:
        a = datetime(2026, 9, 23, 8, 47, tzinfo=timezone.utc)  # 04:47 ET
        self.assertTrue(_data_hole(a, a + timedelta(minutes=140)))


if __name__ == "__main__":
    unittest.main()
