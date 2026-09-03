"""Phase 38 concurrent Pine patch tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from phase36.data import load_replay_market_15m
from phase37.concurrent import _midpoint_reclaimed, replay_concurrent

from phase38.config import (
    EXP_CONT_L,
    EXP_CONT_S,
    EXP_PINE_POOL_CAP,
    EXP_REV_RL,
    EXP_REV_RS,
    EXP_REV_TOTAL,
    P37_REFERENCE_MAP,
    RESULTS,
)
from phase38.parity import compare_signals, load_reference, run_pine_equivalent_replay
from phase38.run import run_phase38


ROOT = Path(__file__).resolve().parents[2]
IND_PATH = RESULTS / "NQ_15M_COMBINED_INDICATOR_CONCURRENT.pine"
STR_PATH = RESULTS / "NQ_15M_COMBINED_STRATEGY_CONCURRENT.pine"
OLD_IND = ROOT / "phase34" / "results" / "combined_pine" / "NQ_15M_COMBINED_INDICATOR.pine"


class ConcurrentPinePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        os.environ["PHASE38_SKIP_REPLAY"] = "1"
        cls.manifest = run_phase38()
        cls.reference = load_reference()
        cls.parity = pd.read_csv(RESULTS / "pine_parity.csv")

    def test_deliverables_exist(self):
        for name in (
            "NQ_15M_COMBINED_INDICATOR_CONCURRENT.pine",
            "NQ_15M_COMBINED_STRATEGY_CONCURRENT.pine",
            "pine_parity.csv",
            "parity_windows.csv",
            "signal_counts.csv",
            "study_manifest.json",
            "CONCURRENT_PINE_PATCH_REPORT.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_original_phase34_pine_unmodified(self):
        old = OLD_IND.read_text()
        self.assertIn("var int   rvState = ST_IDLE", old)
        self.assertNotIn("FZ_RV_POOL_CAP", old)

    def test_concurrent_pine_structure(self):
        ind = IND_PATH.read_text()
        self.assertIn("FZ_RV_POOL_CAP     = 8", ind)
        self.assertIn("type ReversalCand", ind)
        self.assertIn("array<ReversalCand> rvPool", ind)
        self.assertIn("midpointReclaimed(c.dispDir, c.mid)", ind)
        self.assertNotIn("var int   rvState = ST_IDLE", ind)
        self.assertIn('text = "RL"', ind)
        self.assertIn("size.tiny", ind)
        self.assertIn('input.bool(false, "Show Debug"', ind)
        self.assertIn("barstate.isconfirmed", ind)
        self.assertNotIn("lookahead_on", ind)

    def test_continuation_constants_unchanged(self):
        ind = IND_PATH.read_text()
        old = OLD_IND.read_text()
        for token in (
            "FZ_P31_TARGET_R    = 3.0",
            "FZ_P31_STOP_ATR    = 0.75",
            "FZ_P31_MAX_HOLD    = 4",
            "FZ_BOS_RETEST_WIN  = 2",
        ):
            self.assertIn(token, ind)
            self.assertIn(token, old)

    def test_midpoint_reclaim_uses_displacement_direction(self):
        self.assertTrue(_midpoint_reclaimed("Short", 100.0, 101.0))
        self.assertTrue(_midpoint_reclaimed("Long", 100.0, 99.0))
        self.assertFalse(_midpoint_reclaimed("Long", 100.0, 101.0))

    def test_reference_reversal_counts(self):
        rl = int((self.reference["signal_type"] == "RL").sum())
        rs = int((self.reference["signal_type"] == "RS").sum())
        self.assertEqual(rl, EXP_REV_RL)
        self.assertEqual(rs, EXP_REV_RS)
        self.assertEqual(rl + rs, EXP_REV_TOTAL)

    def test_reference_continuation_counts(self):
        l = int((self.reference["signal_type"] == "L").sum())
        s = int((self.reference["signal_type"] == "S").sum())
        self.assertEqual(l, EXP_CONT_L)
        self.assertEqual(s, EXP_CONT_S)

    def test_pine_equivalent_exact_parity(self):
        actual = run_pine_equivalent_replay()
        parity = compare_signals(self.reference, actual)
        self.assertEqual((parity["parity_status"] == "MATCH").sum(), len(parity))
        self.assertEqual((parity["parity_status"] == "MISSING").sum(), 0)
        self.assertEqual((parity["parity_status"] == "EXTRA").sum(), 0)

    def test_deterministic_replay(self):
        market = load_replay_market_15m().iloc[:5000]
        a, _, _ = replay_concurrent(market)
        b, _, _ = replay_concurrent(market)
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_dtype=False)

    def test_concurrent_beats_single_tracker(self):
        rev_ref = int((self.reference["signal_type"].isin(["RL", "RS"])).sum())
        self.assertGreater(rev_ref, 1299)

    def test_manifest_audit(self):
        m = json.loads((RESULTS / "study_manifest.json").read_text())
        self.assertTrue(m["continuation"]["parity_pass"])
        self.assertTrue(m["reversal"]["parity_pass"])
        self.assertEqual(m["conflict_policy"], "INDEPENDENT")
        self.assertEqual(m["pine_pool_capacity"], EXP_PINE_POOL_CAP)

    def test_parity_windows_nonempty(self):
        windows = pd.read_csv(RESULTS / "parity_windows.csv")
        self.assertGreater(len(windows), 10)
        for wid in ("RESTORED_RL", "CONTINUATION_L", "ERA_2024"):
            self.assertTrue((windows["window_id"] == wid).any(), wid)


if __name__ == "__main__":
    unittest.main()
