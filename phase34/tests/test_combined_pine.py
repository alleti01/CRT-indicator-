"""Phase 34 combined Pine tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase29.config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS
from phase29.simulator import SimConfig, resolve_entry, simulate_trade
from phase32.parity import extract_frozen_signals, frozen_sim_config
from phase33.config import WF_FAILURE_DEFS
from phase33.failure import build_failure_events, failure_signals, _midpoint_reclaim
from phase33.displacements import scan_displacements, precompute_opposite_bos
from phase33.entries import resolve_reclaim_retest
from phase31.data import load_market_15m
from phase31.dedupe import dedupe_signals

from phase34.config import (
    P31_ARCH,
    P33_ARCH,
    P33_FAILURE_DEF,
    P33_FAILURE_WINDOW,
    P33_MAX_HOLD_BARS,
    P33_STOP_ATR,
    P33_TARGET_R,
    RESULTS,
    RTH_SESSION,
)
from phase34.parity import build_combined_reference, frozen_p33_config
from phase34.run import run_phase34


ROOT = Path(__file__).resolve().parents[2]


class CombinedPineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = run_phase34()
        cls.combined, cls.windows, cls.counts, cls.meta, cls.visual_windows, cls.placement_diag = build_combined_reference()

    def test_deliverables_exist(self):
        for name in (
            "NQ_15M_COMBINED_INDICATOR.pine",
            "NQ_15M_COMBINED_STRATEGY.pine",
            "combined_parity_reference.csv",
            "parity_windows.csv",
            "signal_count_parity.csv",
            "study_manifest.json",
            "PINE_VALIDATION_CHECKLIST.md",
            "COMBINED_PINE_IMPLEMENTATION_REPORT.md",
        ):
            self.assertTrue((RESULTS / name).exists(), name)

    def test_pine_enforces_15m_and_no_lookahead(self):
        ind = (RESULTS / "NQ_15M_COMBINED_INDICATOR.pine").read_text()
        self.assertIn('timeframe.period == "15"', ind)
        self.assertIn("barstate.isconfirmed", ind)
        self.assertNotIn("lookahead_on", ind)
        self.assertNotIn("location.absolute", ind)

    def test_pine_frozen_constants_and_markers(self):
        ind = (RESULTS / "NQ_15M_COMBINED_INDICATOR.pine").read_text()
        self.assertIn("FZ_P31_TARGET_R    = 3.0", ind)
        self.assertIn("FZ_P33_TARGET_R    = 2.5", ind)
        self.assertIn("FZ_P33_FAIL_WIN    = 4", ind)
        self.assertIn('text = "L"', ind)
        self.assertIn('text = "RL"', ind)
        self.assertIn('input.bool(false, "Show Debug"', ind)
        self.assertIn('input.bool(false, "Show Placement Debug"', ind)
        self.assertIn("location.belowbar", ind)
        self.assertIn("location.abovebar", ind)
        self.assertIn("xloc.bar_index", ind)
        self.assertIn("yloc.price", ind)
        self.assertIn("p31HistE", ind)
        self.assertIn("size.tiny", ind)

    def test_indicator_no_scale_polluting_plots(self):
        ind = (RESULTS / "NQ_15M_COMBINED_INDICATOR.pine").read_text()
        self.assertNotIn("location.absolute", ind)
        # No unconditional overlay plots of state/diagnostic series
        for bad in ("plot(p31State", "plot(rvState", "plot(atrVal", "plot(closeLoc", "plot(barBody"):
            self.assertNotIn(bad, ind)

    def test_price_level_sanity_helper(self):
        ind = (RESULTS / "NQ_15M_COMBINED_INDICATOR.pine").read_text()
        self.assertIn("priceLevelOk", ind)
        self.assertIn("tradeLevelsOk", ind)

    def test_signal_count_unchanged_by_visual_patch(self):
        row = self.counts.loc[self.counts.signal_type == "ALL"].iloc[0]
        self.assertEqual(int(row.python_count), 5642)
        self.assertEqual(int(row.difference), 0)

    def test_p31_displacement_parity(self):
        market = load_market_15m()
        signals = extract_frozen_signals(market)
        self.assertGreater(len(signals), 3000)
        for ts in signals["entry_timestamp"].head(20):
            self.assertTrue(is_in_session(pd.Timestamp(ts), RTH_SESSION))

    def test_p31_bos_retest_ordering(self):
        tz = "America/Chicago"
        idx = pd.date_range("2024-06-03 09:30", periods=6, freq="15min", tz=tz)
        market = pd.DataFrame(
            {
                "open": [100.0] * 6,
                "high": [101.0, 105.0, 104.0, 103.0, 103.0, 103.0],
                "low": [99.0, 99.0, 100.5, 100.0, 100.0, 100.0],
                "close": [100.0, 104.0, 101.0, 102.0, 102.0, 102.0],
                "volume": [100] * 6,
                "atr": [2.0] * 6,
            },
            index=idx,
        )
        pos_map = {ts: i for i, ts in enumerate(market.index)}
        sig = pd.Series({"signal_id": 1, "direction": "Long", "entry_timestamp": idx[1], "bos_timestamp": idx[1]})
        ok, entry_i, entry_px, _ = resolve_entry(sig, market, pos_map, "BOS_RETEST")
        self.assertTrue(ok)
        self.assertEqual(entry_i, 2)

    def test_p33_midpoint_reclaim_within_four_bars(self):
        market = load_market_15m()
        displacements = scan_displacements(market)
        for _, disp in displacements.iterrows():
            hit = _midpoint_reclaim(disp, market, P33_FAILURE_WINDOW)
            if hit is not None:
                j, _, _ = hit
                self.assertLessEqual(j - int(disp["bar_index"]), P33_FAILURE_WINDOW)
                return
        self.fail("expected at least one midpoint reclaim within failure window")

    def test_p33_reclaim_retest_ordering(self):
        tz = "America/Chicago"
        idx = pd.date_range("2024-06-03 09:30", periods=6, freq="15min", tz=tz)
        market = pd.DataFrame(
            {
                "open": [100.0] * 6,
                "high": [101.0, 101.0, 101.5, 101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 99.5, 99.8, 100.0, 100.0],
                "close": [100.0, 99.5, 100.5, 100.2, 100.0, 100.0],
                "volume": [100] * 6,
                "atr": [2.0] * 6,
            },
            index=idx,
        )
        pos_map = {ts: i for i, ts in enumerate(market.index)}
        sig = pd.Series({"signal_id": 1, "direction": "Long", "entry_timestamp": idx[2], "reclaim_level": 100.0})
        ok, entry_i, _, _ = resolve_reclaim_retest(sig, market, pos_map)
        self.assertTrue(ok)
        self.assertGreater(entry_i, 2)

    def test_stop_target_hold_frozen(self):
        cfg = frozen_sim_config()
        self.assertEqual(cfg.stop_atr, 0.75)
        self.assertEqual(cfg.target_r, 3.0)
        self.assertEqual(cfg.max_bars, 4)
        p33 = frozen_p33_config()
        self.assertEqual(p33["stop_atr"], P33_STOP_ATR)
        self.assertEqual(p33["target_r"], P33_TARGET_R)
        self.assertEqual(p33["max_bars"], P33_MAX_HOLD_BARS)

    def test_combined_reference_integrity(self):
        self.assertGreater(len(self.combined), 4000)
        self.assertIn(P31_ARCH, set(self.combined.architecture))
        self.assertIn(P33_ARCH, set(self.combined.architecture))
        p31 = self.combined.loc[self.combined.architecture == P31_ARCH]
        p33 = self.combined.loc[self.combined.architecture == P33_ARCH]
        self.assertGreater(len(p31), 3000)
        self.assertGreater(len(p33), 1500)

    def test_signal_count_parity_table(self):
        row = self.counts.loc[self.counts.signal_type == "ALL"].iloc[0]
        self.assertEqual(int(row.python_count), len(self.combined))

    def test_parity_windows_created(self):
        self.assertGreaterEqual(len(self.windows), 8)
        for wid in ("CONTINUATION_LONG", "REVERSAL_LONG", "ERA1", "RECENT_2025"):
            self.assertTrue((self.windows.window_id == wid).any(), wid)

    def test_conflict_independent_in_manifest(self):
        self.assertEqual(json.loads((RESULTS / "study_manifest.json").read_text())["conflict_policy"], "INDEPENDENT")

    def test_p33_failure_def_frozen(self):
        self.assertEqual(P33_FAILURE_DEF, "A_MID_4")
        self.assertIn("A_MID_4", WF_FAILURE_DEFS)


if __name__ == "__main__":
    unittest.main()
