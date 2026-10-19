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
        moved = bars[:1000] + [Bar(b.timestamp, b.open + 500, b.high + 500, b.low + 500, b.close + 500) for b in bars[1000:]]
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


class GapTests(unittest.TestCase):
    def test_daily_break_is_not_a_hole(self) -> None:
        a = datetime(2026, 9, 22, 21, 0, tzinfo=timezone.utc)  # 17:00 ET
        self.assertFalse(_data_hole(a, a + timedelta(minutes=61)))

    def test_overnight_hole_is_a_hole(self) -> None:
        a = datetime(2026, 9, 23, 8, 47, tzinfo=timezone.utc)  # 04:47 ET
        self.assertTrue(_data_hole(a, a + timedelta(minutes=140)))


if __name__ == "__main__":
    unittest.main()
