"""Phase 37 concurrent reversal parity tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from phase36.data import load_replay_market_15m
from phase37.config import RESULTS
from phase37.concurrent import replay_concurrent, _midpoint_reclaimed
from phase37.metrics import load_phase33_batch_fills
from phase37.run import run_phase37


class ConcurrentReversalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["PHASE37_SKIP_REPLAY"] = "1"
        cls.manifest = run_phase37(skip_replay=True)

    def test_deliverables_exist(self):
        for name in (
            "concurrent_reversal_signal_map.csv",
            "candidate_state_log.csv",
            "phase33_parity.csv",
            "single_vs_concurrent.csv",
            "restored_signal_analysis.csv",
            "same_bar_conflicts.csv",
            "continuation_reversal_conflicts.csv",
            "yearly_results.csv",
            "cost_stress.csv",
            "concurrency_statistics.csv",
            "pine_reference_map.csv",
            "research_manifest.json",
            "CONCURRENT_REVERSAL_PARITY_REPORT.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_midpoint_reclaim_long_disp(self):
        self.assertTrue(_midpoint_reclaimed("Long", 100.0, 99.0))
        self.assertFalse(_midpoint_reclaimed("Long", 100.0, 101.0))

    def test_midpoint_reclaim_short_disp(self):
        self.assertTrue(_midpoint_reclaimed("Short", 100.0, 101.0))

    def test_ls_unchanged_vs_phase36(self):
        m = self.manifest.get("phase31_ls_parity", {})
        self.assertGreater(m.get("match_pct", 0), 0.999)

    def test_exact_phase33_reversal_parity(self):
        self.assertEqual(
            self.manifest.get("original_phase33_RL", 0) + self.manifest.get("original_phase33_RS", 0),
            self.manifest.get("phase37_RL", 0) + self.manifest.get("phase37_RS", 0),
        )
        self.assertAlmostEqual(self.manifest.get("match_rate_vs_batch", 0), 1.0, places=3)

    def test_deterministic(self):
        market = load_replay_market_15m().iloc[:4000]
        s1, _, _ = replay_concurrent(market)
        s2, _, _ = replay_concurrent(market)
        pd.testing.assert_frame_equal(
            s1.reset_index(drop=True),
            s2.reset_index(drop=True),
            check_dtype=False,
        )

    def test_concurrent_beats_single_tracker_count(self):
        self.assertGreater(
            self.manifest.get("phase37_RL", 0) + self.manifest.get("phase37_RS", 0),
            self.manifest.get("phase36_RL", 0) + self.manifest.get("phase36_RS", 0),
        )

    def test_manifest_audit(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertEqual(m["lookahead_audit"], "PASS")
        self.assertEqual(m["deterministic"], "PASS")

    def test_batch_parity_entry_prices(self):
        market = load_replay_market_15m().iloc[:5000]
        batch = load_phase33_batch_fills(market)
        concurrent, _, _ = replay_concurrent(market)
        rev = concurrent.loc[concurrent["signal_type"].isin(["RL", "RS"])]
        if batch.empty:
            return
        batch["t"] = pd.to_datetime(batch["entry_timestamp"], utc=True).dt.floor("15min")
        batch["st"] = batch["direction"].map({"Long": "RL", "Short": "RS"})
        rev["t"] = pd.to_datetime(rev["marker_bar_timestamp"], utc=True).dt.floor("15min")
        m = rev.merge(batch, left_on=["t", "signal_type"], right_on=["t", "st"])
        self.assertEqual(len(m), len(batch))
        self.assertLess((m["entry_price_x"] - m["entry_price_y"]).abs().max(), 0.01)


if __name__ == "__main__":
    unittest.main()
