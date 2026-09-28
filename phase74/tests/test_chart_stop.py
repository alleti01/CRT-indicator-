"""The broker stop is the chart stop, measured from the fill."""
from __future__ import annotations

import unittest

from phase74.runtime.chart_stop import chart_stop_for_fill


class ChartStopTests(unittest.TestCase):
    def test_short_stop_stays_above_the_fill(self) -> None:
        applied = chart_stop_for_fill("SHORT", 30650.0, 30664.25)
        self.assertEqual(applied, (30664.25, 14.25))

    def test_long_stop_stays_below_the_fill(self) -> None:
        applied = chart_stop_for_fill("LONG", 30650.0, 30635.75)
        self.assertEqual(applied, (30635.75, 14.25))

    def test_stop_already_through_the_fill_is_rejected(self) -> None:
        self.assertIsNone(chart_stop_for_fill("SHORT", 30670.0, 30664.25))
        self.assertIsNone(chart_stop_for_fill("LONG", 30620.0, 30635.75))
