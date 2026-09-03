"""Phase 40 tests."""

from __future__ import annotations

import json
import unittest

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m

from phase40.config import EXP_TOTAL, IMPULSE_THRESHOLD, P37_SIGNAL_MAP, P39_FULL_FILTERED_AVGR, P39_OOS_FILTERED_AVGR, RESULTS
from phase40.filter import apply_filter, attach_entry_impulse, compute_impulse_3bar
from phase40.run import run_phase40, verify_unfiltered_parity


class Phase40Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = run_phase40()
        cls.market = load_replay_market_15m()
        cls.signals = pd.read_csv(P37_SIGNAL_MAP)
        cls.signals["marker_bar_timestamp"] = pd.to_datetime(cls.signals["marker_bar_timestamp"], utc=True)

    def test_deliverables(self):
        for name in (
            "filtered_signal_map.csv",
            "rejected_signal_map.csv",
            "pine_reference_map.csv",
            "signal_type_results.csv",
            "yearly_results.csv",
            "cost_stress.csv",
            "parity_windows.csv",
            "PINE_IMPLEMENTATION_REPORT.md",
            "research_manifest.json",
            "NQ15_COMBINED_PHASE40.pine",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_unfiltered_parity(self):
        p = verify_unfiltered_parity(self.signals)
        self.assertTrue(p["parity_pass"])
        self.assertEqual(p["counts"]["total"], EXP_TOTAL)

    def test_impulse_calculation(self):
        imp = compute_impulse_3bar(self.market)
        self.assertIn("impulse_3bar", imp.name if hasattr(imp, "name") else imp)
        self.assertTrue((imp.dropna() >= 0).all())

    def test_threshold_boundary(self):
        all_sig, acc, rej = apply_filter(self.signals, self.market)
        self.assertTrue((acc["impulse_3bar"] >= IMPULSE_THRESHOLD).all())
        self.assertTrue((rej["impulse_3bar"] < IMPULSE_THRESHOLD).all())
        self.assertEqual(len(acc) + len(rej), len(all_sig))

    def test_retention_approx_65pct(self):
        all_sig, acc, _ = apply_filter(self.signals, self.market)
        ret = len(acc) / len(all_sig)
        self.assertGreater(ret, 0.60)
        self.assertLess(ret, 0.72)

    def test_no_lookahead(self):
        feats = attach_entry_impulse(self.signals.head(50), self.market)
        pos = {ts: i for i, ts in enumerate(self.market.index)}
        for row in feats.itertuples():
            ts = pd.Timestamp(row.marker_bar_timestamp)
            i = pos[ts]
            close = float(self.market.iloc[i]["close"])
            close_3 = float(self.market.iloc[i - 3]["close"]) if i >= 3 else np.nan
            atr = float(self.market.iloc[i]["atr"])
            expected = abs(close - close_3) / atr if i >= 3 and atr > 0 else np.nan
            if np.isfinite(expected):
                self.assertAlmostEqual(row.impulse_3bar, expected, places=6)

    def test_pine_reference_accepted_only(self):
        ref = pd.read_csv(RESULTS / "pine_reference_map.csv")
        rej = pd.read_csv(RESULTS / "rejected_signal_map.csv")
        self.assertTrue((ref["impulse_3bar"] >= IMPULSE_THRESHOLD).all())
        keys_ref = set(zip(pd.to_datetime(ref["timestamp"], utc=True), ref["signal_type"]))
        keys_rej = set(zip(pd.to_datetime(rej["marker_bar_timestamp"], utc=True), rej["signal_type"]))
        self.assertEqual(len(keys_ref & keys_rej), 0)

    def test_phase39_reproduction(self):
        m = json.loads((RESULTS / "research_manifest.json").read_text())
        self.assertTrue(m["phase39_reproduction"]["reproduced"])

    def test_pine_has_impulse_filter(self):
        pine = (RESULTS / "NQ15_COMBINED_PHASE40.pine").read_text()
        self.assertIn("FZ_IMPULSE_MIN", pine)
        self.assertIn("impulsePass", pine)
        self.assertIn("Show Rejected Signals", pine)


if __name__ == "__main__":
    unittest.main()
