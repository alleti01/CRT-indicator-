"""Pre-entry features and MNQ stop sizing. No order path is involved."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pathlib import Path
from tempfile import TemporaryDirectory

from forward_rehearsal.research.cdx_preentry_filter import (
    Bar,
    Three,
    adverse_displacement,
    append_shadow_record,
    atr14,
    completed_threes,
    efficiency,
    features_at,
    flip_count,
    overlap,
    shadow_decision,
    size_mnq,
)

BASE = datetime(2026, 9, 29, 13, 0, tzinfo=timezone.utc)


def _bar(i: int, high: float, low: float, close: float) -> Bar:
    return Bar(BASE + timedelta(minutes=i), high, low, close)


class PreentryTests(unittest.TestCase):
    def test_adverse_long_and_short(self) -> None:
        self.assertEqual(adverse_displacement("LONG", 100, 104), 4)
        self.assertEqual(adverse_displacement("SHORT", 100, 96), 4)
        self.assertLess(adverse_displacement("SHORT", 30591.75, 30602.0), 0)

    def test_golden_951_risk(self) -> None:
        distance = abs(30602.0 - 30638.25)
        self.assertEqual(distance, 36.25)
        qty50, reason50, risk = size_mnq(30602.0, 30638.25, 50)
        qty75, reason75, _ = size_mnq(30602.0, 30638.25, 75)
        qty100, reason100, _ = size_mnq(30602.0, 30638.25, 100)
        qty150, reason150, _ = size_mnq(30602.0, 30638.25, 150)
        self.assertEqual(risk, 72.50)
        self.assertEqual((qty50, reason50), (0, "RISK_MIN_CONTRACT_EXCEEDS_CAP"))
        self.assertEqual((qty75, reason75), (1, "RISK_ACCEPT"))
        self.assertEqual((qty100, reason100), (1, "RISK_ACCEPT"))
        self.assertEqual((qty150, reason150), (2, "RISK_ACCEPT"))
        self.assertEqual(36.25 * 2 * 7, 507.50)

    def test_stop_is_not_rewritten_to_fit_the_cap(self) -> None:
        stop = 30638.25
        size_mnq(30602.0, stop, 50)
        self.assertEqual(stop, 30638.25)

    def test_efficiency_and_overlap_and_atr(self) -> None:
        self.assertEqual(efficiency([1, 2, 3, 4]), 1.0)
        self.assertAlmostEqual(efficiency([1, 3, 2, 4]), 3 / 5)
        bars = [
            Three(BASE, 10, 8, 9),
            Three(BASE + timedelta(minutes=3), 11, 9, 10),
        ]
        self.assertGreater(overlap(bars), 0)
        series = []
        for i in range(15):
            series.append(Three(BASE + timedelta(minutes=3 * i), 10 + i, 8 + i, 9 + i))
        self.assertIsNotNone(atr14(series))
        self.assertGreater(atr14(series), 0)

    def test_flip_count_uses_only_signals_inside_the_window(self) -> None:
        window = [Three(BASE + timedelta(minutes=3 * i), 1, 0, 1) for i in range(6)]
        asof = window[-1].close_time
        signals = [
            (BASE - timedelta(hours=5), "LONG"),
            (window[1].open_time, "SHORT"),
            (window[3].open_time, "LONG"),
            (asof + timedelta(minutes=3), "SHORT"),
        ]
        self.assertEqual(flip_count(signals, asof, window), 1)

    def test_future_bar_does_not_change_features(self) -> None:
        bars = [_bar(i, 100 + (i % 3), 99, 100) for i in range(90)]
        asof = bars[60].close_time
        signals = [(bars[10].open_time, "LONG"), (bars[40].open_time, "SHORT")]
        full = features_at(
            bars, signals, asof=asof, side="SHORT", cdx_entry=100, fill=101, sl=110, tp1=90
        )
        truncated = features_at(
            bars[:61], signals, asof=asof, side="SHORT", cdx_entry=100, fill=101, sl=110, tp1=90
        )
        self.assertEqual(full, truncated)
        leaked = completed_threes(bars, bars[-1].close_time)
        known = completed_threes(bars, asof)
        self.assertGreater(len(leaked), len(known))

    def test_shadow_decision_does_not_change_quantity(self) -> None:
        order = {"quantity": 7, "stop": 30638.25}
        decision = shadow_decision({"f1_recent_whipsaw": True, "f2_adverse_fill": False})
        self.assertEqual(order["quantity"], 7)
        self.assertEqual(order["stop"], 30638.25)
        self.assertEqual(decision["SHADOW_DECISION"], "WOULD_TAKE")
        self.assertIsNone(decision["F3_RIBBON_CONFLICT"])

    def test_shadow_log_is_append_only_and_leaves_the_order(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "shadow.jsonl"
            order = {"quantity": 7, "stop": 30638.25}
            first = append_shadow_record(path, {"f1_recent_whipsaw": False, "f2_adverse_fill": True}, order)
            second = append_shadow_record(path, {"f1_recent_whipsaw": True, "f2_adverse_fill": False}, order)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(first, order)
            self.assertEqual(second["quantity"], 7)
            self.assertEqual(order["stop"], 30638.25)


if __name__ == "__main__":
    unittest.main()
