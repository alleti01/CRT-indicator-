"""Unswept-wick target matches the CDX signals-only mirror stop."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from phase73.market_data.bar import Bar
from phase74.quality.wick_targets import wick_targets


def _bar(minute: int, high: float, low: float, close: float) -> Bar:
    return Bar(
        timestamp=datetime(2026, 9, 24, 18, 0, tzinfo=timezone.utc) + timedelta(minutes=minute * 3),
        open=close,
        high=high,
        low=low,
        close=close,
    )


class WickTargetTests(unittest.TestCase):
    def test_far_wick_of_nearest_cluster_and_next_wick(self) -> None:
        bars = []
        # Swing high at 100, then a higher untouched high at 103 (same cluster), then 140.
        for minute, high, low in (
            (0, 130, 80),
            (1, 135, 81),
            (2, 140, 82),
            (3, 120, 83),
            (4, 110, 84),
            (5, 96, 85),
            (6, 100, 86),
            (7, 94, 87),
            (8, 93, 88),
            (9, 103, 89),
            (10, 96, 90),
            (11, 95, 91),
            (12, 94, 92),
        ):
            bars.append(_bar(minute, high, low, (high + low) / 2))
        found = wick_targets("LONG", 90.0, bars, bars[-1].timestamp)
        self.assertIsNotNone(found)
        assert found is not None
        first, second = found
        self.assertEqual(first, 103.0)
        self.assertEqual(second, 140.0)


if __name__ == "__main__":
    unittest.main()
