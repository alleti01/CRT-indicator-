"""Causal checks for the offline CDX consolidation replay."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from forward_rehearsal.research.cdx_directional_consolidation import (
    Bar,
    causality_mismatches,
    run_sim,
)

BASE = datetime(2026, 9, 29, 6, 0, tzinfo=timezone.utc)


def _bar(i: int, high: float, low: float, close: float | None = None) -> Bar:
    return Bar(BASE + timedelta(minutes=i), high, low, close if close is not None else (high + low) / 2)


def _flat(start: int, end: int, high: float, low: float) -> list[Bar]:
    return [_bar(i, high, low) for i in range(start, end)]


class ConsolidationReplayTests(unittest.TestCase):
    def test_chop_before_half_r_does_not_exit_or_tighten(self) -> None:
        bars = [_bar(0, 101, 100)] + _flat(1, 40, 104, 99)
        sim = run_sim(
            bars,
            side="LONG",
            fill=100,
            sl=90,
            tp1=140,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V2",
        )
        self.assertEqual(sim.stop, 90)
        self.assertFalse(sim.armed)
        self.assertEqual(sim.result.reason, "DATA_END")
        self.assertIsNone(sim.legacy)

    def test_arm_bar_does_not_change_the_stop(self) -> None:
        bars = [_bar(0, 101, 100), _bar(1, 106, 101), _bar(2, 104, 103)]
        sim = run_sim(
            bars,
            side="LONG",
            fill=100,
            sl=90,
            tp1=140,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V2",
        )
        self.assertTrue(sim.armed)
        self.assertEqual(sim.armed_time, BASE + timedelta(minutes=2))
        self.assertEqual(sim.stops_at_open[0], 90)

    def test_post_arm_pivot_tightens_on_the_next_bar_only(self) -> None:
        bars = [
            _bar(0, 101, 100.5),
            _bar(1, 101, 100.5),
            _bar(2, 106, 104),  # arms at 06:03, inside the first 3m bucket
        ]
        bars += _flat(3, 6, 105, 104)  # 06:03 bucket low 104
        bars += _flat(6, 9, 104, 102)  # center low 102
        bars += _flat(9, 12, 104, 103)  # right low 103, confirms as 06:12 opens
        bars.append(_bar(12, 104, 102.5))
        bars.append(_bar(13, 104, 101.5))
        sim = run_sim(
            bars,
            side="LONG",
            fill=100,
            sl=90,
            tp1=140,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V2",
        )
        self.assertEqual(sim.result.reason, "STRUCTURAL_STOP")
        self.assertEqual(sim.result.price, 101.75)
        self.assertGreater(sim.result.bar_index, 0)
        self.assertEqual(sim.stops_at_open[0], 90)

    def test_same_bar_stop_and_target_is_the_stop(self) -> None:
        bars = [_bar(0, 100, 100), _bar(1, 141, 89)]
        sim = run_sim(
            bars,
            side="LONG",
            fill=100,
            sl=90,
            tp1=130,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V1",
        )
        self.assertEqual(sim.result.reason, "CDX_SL")
        self.assertEqual(sim.result.price, 90)

    def test_short_ratchet_never_loosens(self) -> None:
        bars = [_bar(0, 100, 99)]
        bars.append(_bar(1, 99, 94))  # arms, 0.50R is 95
        bars += _flat(2, 6, 96, 95)
        bars += _flat(6, 9, 98, 95)  # center high 98
        bars += _flat(9, 12, 97, 95)
        bars.append(_bar(12, 97.5, 95))
        sim = run_sim(
            bars,
            side="SHORT",
            fill=100,
            sl=110,
            tp1=70,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V2",
        )
        self.assertTrue(sim.armed)
        self.assertLessEqual(sim.stop, 110)
        if sim.revisions:
            self.assertLess(sim.revisions[-1][1], 110)

    def test_prefix_replay_matches_the_full_path(self) -> None:
        bars = [_bar(0, 101, 100.5), _bar(1, 101, 100.5), _bar(2, 106, 104)]
        bars += _flat(3, 6, 105, 104)
        bars += _flat(6, 9, 104, 102)
        bars += _flat(9, 12, 104, 103)
        bars.append(_bar(12, 104, 102.5))
        bars.append(_bar(13, 104, 101.5))
        mismatches = causality_mismatches(
            bars,
            side="LONG",
            fill=100,
            sl=90,
            tp1=140,
            cdx_entry=100,
            fill_time=BASE + timedelta(seconds=30),
            variant="V2",
            qty=7,
        )
        self.assertEqual(mismatches, 0)


if __name__ == "__main__":
    unittest.main()
