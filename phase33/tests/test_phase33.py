"""Phase 33 tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from phase31.data import load_market_15m

from phase33.config import RESULTS, WF_FAILURE_DEFS
from phase33.displacements import precompute_opposite_bos, scan_displacements
from phase33.failure import build_failure_events, classify_continuation_vs_failure, failure_signals
from phase33.run import run_phase33


ROOT = Path(__file__).resolve().parents[2]


class Phase33Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest_path = RESULTS / "research_manifest.json"
        if not manifest_path.exists():
            cls.manifest = run_phase33()
        else:
            cls.manifest = json.loads(manifest_path.read_text())

    def test_results_generated(self):
        self.assertTrue((RESULTS / "failure_events.csv").exists())
        self.assertTrue((RESULTS / "walk_forward_trades.csv").exists())
        self.assertTrue((RESULTS / "research_manifest.json").exists())
        self.assertTrue((RESULTS / "DISPLACEMENT_FAILURE_REVERSAL_REPORT.md").exists())

    def test_displacement_same_as_phase31_definition(self):
        market = load_market_15m()
        disp = scan_displacements(market)
        self.assertGreater(len(disp), 3000)
        self.assertIn("body_ratio", disp.columns)
        self.assertTrue((disp.body_ratio > 1.5).all())

    def test_failure_definitions_present(self):
        failures = pd.read_csv(RESULTS / "failure_events.csv")
        for prefix in ("A_MID_", "B_OPEN_", "C_EXT_", "D_OPP_BOS", "E_MID_BOS", "E_OPEN_BOS"):
            self.assertTrue(failures.failure_definition.str.contains(prefix.replace("_", "_"), regex=False).any() or failures.failure_definition.str.startswith(prefix.split("_")[0]).any())

    def test_walk_forward_selections_use_preregistered_defs(self):
        sel = pd.read_csv(RESULTS / "walk_forward_selections.csv")
        if not sel.empty:
            self.assertTrue(set(sel.failure_definition).issubset(set(WF_FAILURE_DEFS)))

    def test_continuation_vs_failure_labels(self):
        cont = pd.read_csv(RESULTS / "continuation_vs_failure.csv")
        allowed = {"CONTINUATION", "FAILURE_REVERSAL", "UNRESOLVED"}
        self.assertTrue(set(cont.classification).issubset(allowed))

    def test_manifest_has_classification(self):
        self.assertIn("classification", self.manifest)
        self.assertIn(self.manifest["classification"], {"A", "B", "C", "D"})

    def test_no_lookahead_failure_after_displacement(self):
        market = load_market_15m()
        disp = scan_displacements(market)
        bos, _ = precompute_opposite_bos(market)
        failures = build_failure_events(disp, market, bos)
        for _, row in failures.head(50).iterrows():
            self.assertGreaterEqual(
                pd.Timestamp(row["confirm_timestamp"]),
                pd.Timestamp(row["displacement_timestamp"]),
            )


if __name__ == "__main__":
    unittest.main()
