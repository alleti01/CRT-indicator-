"""Phase 36 full-history replay tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from phase36.config import RESULTS
from phase36.data import load_replay_market_15m
from phase36.parity import compare_to_pine_reference
from phase36.replay import replay_market, _try_bos_retest_fill, _midpoint_reclaimed
from phase36.run import run_phase36


class FullHistoryReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = run_phase36()

    def test_deliverables_exist(self):
        for name in (
            "full_history_signal_map.csv",
            "full_history_state_replay.csv",
            "signal_counts_by_year.csv",
            "signal_counts_by_type.csv",
            "signal_outcomes.csv",
            "historical_visual_windows.csv",
            "python_vs_pine_signal_parity.csv",
            "FULL_HISTORY_SIGNAL_REPLAY_REPORT.md",
            "research_manifest.json",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_deterministic_replay(self):
        market = load_replay_market_15m().iloc[:3000]
        s1, _ = replay_market(market)
        s2, _ = replay_market(market)
        pd.testing.assert_frame_equal(
            s1.reset_index(drop=True),
            s2.reset_index(drop=True),
            check_dtype=False,
        )

    def test_displacement_detection_causal(self):
        market = load_replay_market_15m().iloc[:500]
        _, state = replay_market(market)
        self.assertIn("bullish_displacement", state.columns)
        self.assertFalse(state["L_fire"].sum() > state["bullish_displacement"].sum())

    def test_bos_retest_fill_long(self):
        class Row:
            low = 99.5
            high = 101.0
            close = 100.0

        ok, px = _try_bos_retest_fill(1, 100.0, 0.5, Row())
        self.assertTrue(ok)
        self.assertAlmostEqual(px, 100.0)

    def test_midpoint_reclaim_short_disp(self):
        self.assertTrue(_midpoint_reclaimed(-1, 100.0, 100.5))

    def test_marker_is_entry_bar(self):
        sig = pd.read_csv(RESULTS / "full_history_signal_map.csv")
        if sig.empty:
            return
        self.assertIn("timestamp_ct", sig.columns)
        self.assertIn("retest_time", sig.columns)

    def test_no_outcomes_in_replay_state(self):
        state = pd.read_csv(RESULTS / "full_history_state_replay.csv", nrows=100)
        for col in ("realized_R", "exit_type", "MFE_R"):
            self.assertNotIn(col, state.columns)

    def test_manifest_audit(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertEqual(m["lookahead_audit"], "PASS")
        self.assertEqual(m["deterministic_replay"], "PASS")
        self.assertGreater(m["total_15m_rth_candles"], 10000)

    def test_p34_overlap_continuation_parity(self):
        sig = pd.read_csv(RESULTS / "full_history_signal_map.csv")
        sig["marker_bar_timestamp"] = pd.to_datetime(sig["timestamp_ct"], utc=True)
        parity = compare_to_pine_reference(sig)
        if parity.empty:
            self.skipTest("no parity rows")
        cont = parity.loc[parity["signal_type"].isin(["L", "S"])]
        if cont.empty:
            self.skipTest("no continuation parity rows")
        match_rate = (cont["parity_status"] == "MATCH").mean()
        self.assertGreater(match_rate, 0.95, f"continuation parity {match_rate:.2%}")


if __name__ == "__main__":
    unittest.main()
