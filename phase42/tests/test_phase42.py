"""Phase 42 tests."""

from __future__ import annotations

import json
import unittest

import pandas as pd

from phase42.config import MAX_TPD, MIN_OOS_N, RESULTS
from phase42.dataset import attach_features, build_matched_negatives, load_missed, verify_phase41_parity
from phase42.simulate import cost_stress, enrich_net, monte_carlo, oos_rth_days
from phase42.run import run_phase42


class Phase42Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RESULTS / "research_manifest.json").exists():
            cls.manifest = run_phase42()
        else:
            cls.manifest = json.loads((RESULTS / "research_manifest.json").read_text())

    def test_deliverables(self):
        required = (
            "phase41_parity.csv",
            "missed_reversal_population.csv",
            "matched_negative_controls.csv",
            "reversal_feature_dataset.csv",
            "feature_stability.csv",
            "walk_forward_predictions.csv",
            "precision_frequency_curve.csv",
            "walk_forward_selections.csv",
            "walk_forward_trades.csv",
            "new_only_results.csv",
            "direction_results.csv",
            "yearly_results.csv",
            "cost_stress.csv",
            "outlier_robustness.csv",
            "monte_carlo.csv",
            "false_positive_autopsy.csv",
            "rule_candidates.csv",
            "visual_validation_windows.csv",
            "SPARSE_MISSED_REVERSAL_REPORT.md",
            "research_manifest.json",
        )
        for name in required:
            self.assertTrue((RESULTS / name).exists(), name)

    def test_phase41_parity(self):
        p = verify_phase41_parity()
        missed = p.loc[p["metric"] == "completely_missed", "value"].iloc[0]
        total = p.loc[p["metric"] == "total_major_reversals", "value"].iloc[0]
        self.assertEqual(int(total), 3892)
        self.assertGreater(missed, 1700)
        self.assertLess(missed, 1800)

    def test_positive_and_negative_labels(self):
        ds = pd.read_csv(RESULTS / "reversal_feature_dataset.csv")
        self.assertIn(1, ds["label"].unique())
        self.assertIn(0, ds["label"].unique())
        pos = ds.loc[ds["label"] == 1]
        self.assertGreater(len(pos), 1500)

    def test_negative_controls_exist(self):
        neg = pd.read_csv(RESULTS / "matched_negative_controls.csv")
        self.assertGreater(len(neg.loc[neg["label"] == 0]), 1000)

    def test_walk_forward_isolation(self):
        sel = pd.read_csv(RESULTS / "walk_forward_selections.csv")
        self.assertGreaterEqual(sel["fold"].nunique(), 5)
        self.assertTrue((sel["test_tpd"] <= MAX_TPD).all())

    def test_frequency_on_oos_calendar(self):
        trades = pd.read_csv(RESULTS / "walk_forward_trades.csv")
        tpd = len(trades) / oos_rth_days()
        self.assertLessEqual(tpd, MAX_TPD)

    def test_new_only_segment_reported(self):
        seg = pd.read_csv(RESULTS / "new_only_results.csv")
        self.assertIn("PHASE42_ONLY", seg["segment"].values)

    def test_cost_calculations(self):
        trades = pd.read_csv(RESULTS / "walk_forward_trades.csv")
        t = enrich_net(trades)
        stress = cost_stress(t)
        self.assertEqual(set(stress["cost_multiplier"]), {1.0, 1.5, 2.0})

    def test_outlier_removal(self):
        out = pd.read_csv(RESULTS / "outlier_robustness.csv")
        self.assertIn("exclude_top_1pct", out["slice"].values)

    def test_monte_carlo(self):
        mc = pd.read_csv(RESULTS / "monte_carlo.csv")
        self.assertIn("P_terminal_pos", mc.columns)

    def test_deterministic_replay(self):
        p1 = verify_phase41_parity()
        p2 = verify_phase41_parity()
        pd.testing.assert_frame_equal(p1, p2)

    def test_no_lookahead_audit(self):
        self.assertEqual(self.manifest.get("lookahead_audit"), "PASS")

    def test_oos_sample_size(self):
        self.assertGreaterEqual(self.manifest["oos_performance"]["N"], MIN_OOS_N)


if __name__ == "__main__":
    unittest.main()
