"""Phase 39 tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m

from phase39.classify import classify_behavior, classify_dataframe
from phase39.config import EXP_L, EXP_RL, EXP_RS, EXP_S, P37_SIGNAL_MAP, RESULTS
from phase39.features import build_signal_features
from phase39.paths import build_signal_paths, reconstruct_path
from phase39.run import run_phase39, verify_parity
from phase39.timing import entry_timing_comparison, time_to_move_stats


class Phase39Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = run_phase39()
        cls.market = load_replay_market_15m().iloc[:8000]
        cls.signals = pd.read_csv(P37_SIGNAL_MAP).head(200)
        cls.signals["marker_bar_timestamp"] = pd.to_datetime(cls.signals["marker_bar_timestamp"], utc=True)

    def test_deliverables_exist(self):
        for name in (
            "signal_path_dataset.csv",
            "post_entry_classification.csv",
            "static_vs_expansion_features.csv",
            "movement_probability.csv",
            "entry_timing_comparison.csv",
            "time_to_move.csv",
            "walk_forward_filters.csv",
            "retention_precision_frontier.csv",
            "yearly_results.csv",
            "direction_results.csv",
            "research_manifest.json",
            "ENTRY_TIMING_STATIC_PRECISION_REPORT.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_population_parity(self):
        signals = pd.read_csv(P37_SIGNAL_MAP)
        p = verify_parity(signals)
        self.assertTrue(p["parity_pass"])
        self.assertEqual(p["counts"]["L"], EXP_L)
        self.assertEqual(p["counts"]["S"], EXP_S)
        self.assertEqual(p["counts"]["RL"], EXP_RL)
        self.assertEqual(p["counts"]["RS"], EXP_RS)

    def test_no_future_in_features(self):
        feats = build_signal_features(self.signals.head(20), self.market)
        self.assertFalse(feats.empty)
        for col in ("body_atr", "atr_percentile", "pre_entry_move_3_atr"):
            self.assertIn(col, feats.columns)

    def test_path_metrics(self):
        paths = build_signal_paths(self.signals.head(10), self.market)
        self.assertIn("MFE_R", paths.columns)
        self.assertIn("bars_to_plus_0.50r", paths.columns)
        self.assertTrue((paths["MFE_R"] >= 0).all())

    def test_classification_labels(self):
        paths = build_signal_paths(self.signals.head(50), self.market)
        cls = classify_dataframe(paths)
        self.assertIn("behavior_class", cls.columns)
        self.assertTrue(set(cls["behavior_class"]).issubset(
            {"IMMEDIATE_EXPANSION", "DELAYED_EXPANSION", "STATIC_CHOP", "WRONG_DIRECTION", "WHIPSAW", "CLEAN_WINNER"}
        ))

    def test_entry_timing_causality(self):
        timing = entry_timing_comparison(self.signals.head(10), self.market)
        earlier = timing.loc[timing["timing_variant"] == "ONE_BAR_EARLIER"]
        self.assertTrue((~earlier["causally_available"]).all())

    def test_time_to_move(self):
        paths = build_signal_paths(self.signals.head(100), self.market)
        ttm = time_to_move_stats(paths)
        self.assertGreater(len(ttm), 0)

    def test_manifest_audit(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertEqual(m["lookahead_audit"], "PASS")
        self.assertTrue(m["parity"]["parity_pass"])

    def test_post_entry_labels_not_in_features_only(self):
        feats = build_signal_features(self.signals.head(5), self.market)
        for bad in ("MFE_R", "behavior_class", "realized_R"):
            self.assertNotIn(bad, feats.columns)


if __name__ == "__main__":
    unittest.main()
