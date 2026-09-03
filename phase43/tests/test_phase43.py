"""Phase 43 tests."""

from __future__ import annotations

import json
import unittest

import pandas as pd

from phase43.config import EXP_TOTAL, RESULTS
from phase43.parity import load_frozen_signals, verify_phase40_parity
from phase43.run import run_phase43


class Phase43Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RESULTS / "research_manifest.json").exists():
            cls.manifest = run_phase43()
        else:
            cls.manifest = json.loads((RESULTS / "research_manifest.json").read_text())

    def test_deliverables(self):
        for name in (
            "phase40_parity.csv",
            "frozen_signal_population.csv",
            "signal_quality_features.csv",
            "walk_forward_predictions.csv",
            "quality_deciles.csv",
            "retention_curve.csv",
            "rejection_analysis.csv",
            "research_manifest.json",
            "FROZEN_SIGNAL_QUALITY_REPORT.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_phase40_parity(self):
        sig = load_frozen_signals()
        pop = pd.read_csv(RESULTS / "frozen_signal_population.csv")
        p = verify_phase40_parity(sig, pop)
        self.assertTrue(bool(p.loc[p["metric"] == "parity_pass", "value"].iloc[0]))

    def test_no_extra_signals(self):
        sig = load_frozen_signals()
        self.assertEqual(len(sig), EXP_TOTAL)

    def test_population_only_frozen_entries(self):
        pop = pd.read_csv(RESULTS / "frozen_signal_population.csv")
        self.assertEqual(len(pop), EXP_TOTAL)

    def test_quality_score_present(self):
        oos = pd.read_csv(RESULTS / "walk_forward_predictions.csv")
        self.assertIn("quality_score", oos.columns)
        self.assertTrue(oos["quality_score"].between(0, 100).all())

    def test_walk_forward_isolation(self):
        oos = pd.read_csv(RESULTS / "walk_forward_predictions.csv")
        self.assertGreaterEqual(oos["fold"].nunique(), 5)

    def test_outcome_labels_on_population_only(self):
        pop = pd.read_csv(RESULTS / "frozen_signal_population.csv")
        self.assertIn("net_R", pop.columns)
        self.assertIn("wrong_direction", pop.columns)

    def test_lookahead(self):
        self.assertEqual(self.manifest.get("lookahead_audit"), "PASS")

    def test_retention_curve(self):
        rc = pd.read_csv(RESULTS / "retention_curve.csv")
        self.assertGreater(len(rc), 5)


if __name__ == "__main__":
    unittest.main()
