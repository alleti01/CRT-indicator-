"""Phase 32 Pine parity tests."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase29.config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS
from phase29.simulator import SimConfig, resolve_entry, simulate_trade

from phase32.config import (
    BODY_AVG_LOOKBACK,
    BODY_MULTIPLIER,
    CLOSE_LOC_LONG_MIN,
    CLOSE_LOC_SHORT_MAX,
    MAX_HOLD_BARS,
    RESULTS,
    RTH_SESSION,
    STOP_ATR,
    TARGET_R,
)
from phase32.parity import build_parity_reference, extract_frozen_signals, frozen_sim_config


ROOT = Path(__file__).resolve().parents[2]


class MomentumDisplacementParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.windows, cls.meta = build_parity_reference()

    def test_parity_reference_generated(self):
        self.assertGreater(len(self.reference), 3000)
        path = RESULTS / "pine_parity_reference.csv"
        self.assertTrue(path.exists())

    def test_displacement_body_threshold(self):
        from phase31.data import load_market_15m

        market = load_market_15m()
        body = (market["close"] - market["open"]).abs()
        avg = body.rolling(BODY_AVG_LOOKBACK, min_periods=BODY_AVG_LOOKBACK).mean()
        rng = (market["high"] - market["low"]).replace(0, np.nan)
        cl = (market["close"] - market["low"]) / rng
        signals = extract_frozen_signals(market)
        for _, row in signals.head(20).iterrows():
            ts = pd.Timestamp(row.entry_timestamp)
            i = market.index.get_loc(ts)
            self.assertGreaterEqual(body.iloc[i], BODY_MULTIPLIER * avg.iloc[i])
            if row.direction == "Long":
                self.assertGreaterEqual(cl.iloc[i], CLOSE_LOC_LONG_MIN)
            else:
                self.assertLessEqual(cl.iloc[i], CLOSE_LOC_SHORT_MAX)

    def test_rth_filter(self):
        from phase31.data import load_market_15m

        market = load_market_15m()
        signals = extract_frozen_signals(market)
        for ts in signals["entry_timestamp"]:
            self.assertTrue(is_in_session(pd.Timestamp(ts), RTH_SESSION))

    def test_bos_retest_entry_rules(self):
        tz = "America/Chicago"
        idx = pd.date_range("2024-06-03 09:30", periods=6, freq="15min", tz=tz)
        market = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [101.0, 105.0, 104.0, 103.0, 103.0, 103.0],
                "low": [99.0, 99.0, 100.5, 100.0, 100.0, 100.0],
                "close": [100.0, 104.0, 101.0, 102.0, 102.0, 102.0],
                "volume": [100] * 6,
                "atr": [2.0] * 6,
            },
            index=idx,
        )
        pos_map = {ts: i for i, ts in enumerate(market.index)}
        sig = pd.Series(
            {
                "signal_id": 1,
                "direction": "Long",
                "entry_timestamp": idx[1],
                "bos_timestamp": idx[1],
            }
        )
        ok, entry_i, entry_px, entry_ts = resolve_entry(sig, market, pos_map, "BOS_RETEST")
        self.assertTrue(ok)
        self.assertEqual(entry_i, 2)
        self.assertAlmostEqual(entry_px, 101.0, places=1)

    def test_stop_before_target_ambiguity(self):
        tz = "America/Chicago"
        idx = pd.date_range("2024-06-03 10:00", periods=4, freq="15min", tz=tz)
        market = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0, 100.0],
                "high": [100.5, 105.0, 100.5, 100.5],
                "low": [99.5, 97.0, 99.5, 99.5],
                "close": [100.0, 100.0, 99.5, 99.5],
                "volume": [100] * 4,
                "atr": [2.0] * 4,
            },
            index=idx,
        )
        pos_map = {ts: i for i, ts in enumerate(market.index)}
        sig = pd.Series(
            {
                "signal_id": 1,
                "direction": "Long",
                "entry_timestamp": idx[0],
                "bos_timestamp": idx[0],
            }
        )
        cfg = SimConfig(
            entry_model="CURRENT",
            stop_atr=STOP_ATR,
            target_r=TARGET_R,
            max_bars=MAX_HOLD_BARS,
            management="FIXED",
        )
        res = simulate_trade(sig, market, pos_map, cfg)
        self.assertEqual(res.exit_reason, "STOP")

    def test_deduplication_daily_cap(self):
        from phase31.dedupe import dedupe_signals
        from phase31.data import load_market_15m
        from phase31.signals import _scan_momentum_displacement, filter_rth_signals

        market = load_market_15m()
        raw = filter_rth_signals(_scan_momentum_displacement(market))
        deduped = dedupe_signals(raw, market, max_hold_bars=6)
        self.assertLess(len(deduped), len(raw))

    def test_dry_stretch_audit(self):
        audit = self.meta["dry_stretch_audit"]
        self.assertEqual(audit["correct_full_frozen_longest_dry"], 2)
        self.assertLess(audit["correct_wf_period_longest_dry"], 10)
        self.assertEqual(audit["phase31_reported"], 515)

    def test_full_frozen_not_equal_wf_n(self):
        self.assertNotEqual(len(self.reference), 2873)
        self.assertGreater(len(self.reference), 2873)

    def test_indicator_no_scale_polluting_plots(self):
        path = RESULTS / "MOMENTUM_DISPLACEMENT_15M_FINAL_INDICATOR.pine"
        text = path.read_text()
        self.assertNotIn("location.absolute", text)
        self.assertNotIn("location.bottom", text)
        self.assertNotIn('plotshape(showDebug and smState == ST_WAIT_RETEST', text)
        self.assertIn("Show Debug Markers", text)
        self.assertIn('input.bool(false, "Show Debug Markers"', text)
        self.assertIn('input.bool(false, "Show State Background"', text)


if __name__ == "__main__":
    unittest.main()
