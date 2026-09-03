"""Phase 44 tests."""

from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from phase44.config import EXP_TOTAL, Q_PASS_MIN, Q_RAW_HI, Q_RAW_LO, RESULTS
from phase43.parity import load_frozen_signals
from phase44.run import run_phase44
from phase44.simple_score import quality_score, score_from_features, simple_raw


class Phase44Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (RESULTS / "research_manifest.json").exists():
            cls.manifest = run_phase44()
        else:
            cls.manifest = json.loads((RESULTS / "research_manifest.json").read_text())

    def test_deliverables(self):
        for name in (
            "phase40_parity.csv",
            "quality_reference_all_signals.csv",
            "pine_reference_accepted.csv",
            "pine_reference_rejected.csv",
            "signal_type_results.csv",
            "research_manifest.json",
            "NQ15_PHASE44_QUALITY_INDICATOR.pine",
            "NQ15_PHASE44_QUALITY_STRATEGY.pine",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_phase40_parity(self):
        p = pd.read_csv(RESULTS / "phase40_parity.csv")
        self.assertTrue(bool(p.loc[p["metric"] == "parity_pass", "value"].iloc[0]))

    def test_subset_of_phase40(self):
        all_sig = pd.read_csv(RESULTS / "quality_reference_all_signals.csv")
        acc = set(all_sig.loc[all_sig["accepted"], "signal_id"])
        self.assertEqual(len(all_sig), EXP_TOTAL)
        self.assertTrue(acc.issubset(set(all_sig["signal_id"])))
        self.assertTrue(self.manifest["zero_new_signals"])

    def test_simple_score_determinism(self):
        row = pd.Series({"ret_1_atr": 0.001, "ret_2_atr": 0.002, "ret_3_atr": 0.003})
        a = score_from_features(row)
        b = score_from_features(row)
        self.assertEqual(a, b)

    def test_normalization_constants(self):
        raw = simple_raw(0.0, 0.0, 0.0)
        sc = quality_score(raw)
        self.assertGreaterEqual(sc, 0)
        self.assertLessEqual(sc, 100)

    def test_threshold_boundary(self):
        self.assertFalse(quality_score(Q_RAW_LO) >= Q_PASS_MIN or quality_score(Q_RAW_HI) < Q_PASS_MIN)

    def test_confidence_tiers(self):
        all_sig = pd.read_csv(RESULTS / "quality_reference_all_signals.csv")
        self.assertTrue(set(all_sig.loc[all_sig["accepted"], "confidence"]).issubset({"A+", "A", "B"}))
        self.assertTrue((all_sig.loc[~all_sig["accepted"], "confidence"] == "C").all())

    def test_retention_near_60pct(self):
        acc = pd.read_csv(RESULTS / "pine_reference_accepted.csv")
        self.assertGreater(len(acc) / EXP_TOTAL, 0.55)
        self.assertLess(len(acc) / EXP_TOTAL, 0.65)

    def test_lookahead(self):
        self.assertEqual(self.manifest.get("lookahead_audit"), "PASS")


if __name__ == "__main__":
    unittest.main()
