"""Phase 35 entry re-discovery tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from phase35.config import RESULTS, LABEL_STRONG_TARGET_R, PRIMARY_STOP_ATR
from phase35.discovery import SimpleRule, precision_curve
from phase35.labels import _forward_path
from phase35.run import run_phase35


class EntryRediscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = run_phase35()

    def test_deliverables_exist(self):
        for name in (
            "historical_entry_opportunities.csv",
            "entry_feature_dataset.csv",
            "walk_forward_predictions.csv",
            "long_precision_curve.csv",
            "short_precision_curve.csv",
            "simple_rule_candidates.csv",
            "entry_timing_comparison.csv",
            "yearly_results.csv",
            "direction_results.csv",
            "cost_stress.csv",
            "phase31_phase33_comparison.csv",
            "historical_entry_map.csv",
            "visual_validation_windows.csv",
            "ENTRY_REDISCOVERY_REPORT.md",
            "research_manifest.json",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_no_lookahead_in_features(self):
        from phase35.features import build_features
        from phase31.data import load_market_15m

        m = load_market_15m().iloc[:500]
        f = build_features(m)
        self.assertIn("body_atr", f.columns)
        self.assertNotIn("long_strong", f.columns)

    def test_ambiguous_bar_stop_first(self):
        path = _forward_path(
            1, 100.0, 1.0,
            highs=[102.0], lows=[98.0], closes=[100.5],
            target_r=2.0, max_bars=1,
        )
        self.assertEqual(path["first_event"], "STOP")

    def test_manifest_baseline_rates(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertGreater(m["total_rth_decision_bars"], 10000)
        self.assertGreater(m["baseline_strong_long_rate"], 0)
        self.assertEqual(m["lookahead_audit"], "PASS")

    def test_precision_curve_monotonic_or_documented(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertIn("long_precision_monotonic", m)

    def test_preregistered_label_geometry(self):
        self.assertEqual(LABEL_STRONG_TARGET_R, 2.0)
        self.assertEqual(PRIMARY_STOP_ATR, 0.75)


if __name__ == "__main__":
    unittest.main()
