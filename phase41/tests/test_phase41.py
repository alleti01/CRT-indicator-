"""Phase 41 tests."""

from __future__ import annotations

import json
import unittest

import pandas as pd

from phase36.data import load_replay_market_15m

from phase41.config import PRIMARY_OPPORTUNITY, RESULTS
from phase41.features import build_reversal_features
from phase41.opportunities import label_opportunities
from phase41.run import run_phase41


class Phase41Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RESULTS / "research_manifest.json").exists():
            cls.manifest = run_phase41()
        else:
            cls.manifest = json.loads((RESULTS / "research_manifest.json").read_text())
        cls.market = load_replay_market_15m().loc["2018-01-01":]

    def test_deliverables(self):
        for name in (
            "major_reversal_opportunities.csv",
            "existing_system_capture.csv",
            "missed_reversal_population.csv",
            "true_vs_false_reversal.csv",
            "walk_forward_trades.csv",
            "research_manifest.json",
            "MAJOR_REVERSAL_DISCOVERY_REPORT.md",
            "lookahead_audit.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_opportunities_labeled(self):
        opp = pd.read_csv(RESULTS / "major_reversal_opportunities.csv")
        self.assertGreater(len(opp), 100)
        self.assertIn("event_id", opp.columns)
        self.assertIn("MFE_R", opp.columns)

    def test_no_future_in_features(self):
        feats = build_reversal_features(self.market.iloc[:5000])
        self.assertNotIn("MFE_R", feats.columns)
        self.assertNotIn("future", " ".join(feats.columns).lower())

    def test_capture_statuses(self):
        cap = pd.read_csv(RESULTS / "existing_system_capture.csv")
        self.assertTrue(set(cap["capture_status"]).issubset({"CAPTURED_PHASE33", "CAPTURED_PHASE40", "CAPTURED_OTHER_EXISTING", "MISSED"}))

    def test_walkforward_trades(self):
        wf = pd.read_csv(RESULTS / "walk_forward_trades.csv")
        self.assertGreater(len(wf), 0)

    def test_lookahead_audit(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertEqual(m["lookahead_audit"], "PASS")


if __name__ == "__main__":
    unittest.main()
