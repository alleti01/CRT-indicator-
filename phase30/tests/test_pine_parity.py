"""Phase 30 Pine parity harness tests."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.crt_setup_v2 import (
    SetupV2Archetype,
    SetupV2Detector,
    SetupV2Qualification,
    passes_legacy_qualification,
)
from phase16.models import SetupEvent
from phase16.sequential_bos import SequentialBosConfig, assert_strict_order
from phase16.trade_engine import TradeEngine
from phase29.config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS, hold_bars
from phase29.simulator import SimConfig, resolve_entry, simulate_trade

from phase30.config import MAX_HOLD_BARS, STOP_ATR, TARGET_R
from phase30.parity import build_parity_reference, frozen_sim_config


ROOT = Path(__file__).resolve().parents[2]


class PineParityHarnessTests(unittest.TestCase):
    def test_v2b_next_bar_reclaim_only(self):
        tz = "America/Chicago"
        index = pd.date_range("2026-01-02 09:30", periods=6, freq="15min", tz=tz)
        data = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
                "high": [101.0, 101.0, 101.0, 101.0, 101.0, 101.0],
                "low": [99.0, 99.0, 98.5, 99.5, 99.5, 99.5],
                "close": [100.0, 100.0, 98.8, 100.2, 100.0, 100.0],
                "volume": [100] * 6,
                "atr": [2.0] * 6,
                "crt_high": [101.0, 101.0, 101.0, 101.0, 101.0, 101.0],
                "crt_low": [99.0, 99.0, 99.0, 99.0, 99.0, 99.0],
            },
            index=index,
        )
        config = FrozenConfig(chart_minutes=15)
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.NEXT_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        setup_event = SetupEvent(
            long_setup=False,
            short_setup=False,
            long_score=80,
            short_score=80,
            canonical_long=False,
            canonical_short=False,
            canonical_score=80,
            htf_regime=1,
            session_bucket=2,
        )
        sweep = detector.step(
            bar_index=2,
            timestamp=index[2],
            open_price=100.0,
            high=101.0,
            low=98.5,
            close=98.8,
            atr=2.0,
            crt_high=99.0,
            crt_low=99.0,
            setup_event=setup_event,
            funnel_idle=True,
        )
        self.assertIsNone(sweep)
        reclaim = detector.step(
            bar_index=3,
            timestamp=index[3],
            open_price=100.0,
            high=101.0,
            low=99.5,
            close=100.2,
            atr=2.0,
            crt_high=99.0,
            crt_low=99.0,
            setup_event=setup_event,
            funnel_idle=True,
        )
        self.assertIsNotNone(reclaim)
        self.assertEqual(reclaim.reclaim_mode, "next_bar")

    def test_legacy_qualification_threshold(self):
        config = FrozenConfig()
        setup = SetupEvent(
            long_setup=False,
            short_setup=False,
            long_score=69,
            short_score=80,
            canonical_long=False,
            canonical_short=False,
            canonical_score=69,
            htf_regime=1,
            session_bucket=2,
        )
        self.assertFalse(passes_legacy_qualification(setup, 1, config))
        setup2 = SetupEvent(
            long_setup=False,
            short_setup=False,
            long_score=70,
            short_score=80,
            canonical_long=False,
            canonical_short=False,
            canonical_score=70,
            htf_regime=1,
            session_bucket=2,
        )
        self.assertTrue(passes_legacy_qualification(setup2, 1, config))

    def test_setup_bos_expiry_is_six(self):
        from phase16.crt_setup_v2 import SetupV2Variant, SetupV2Archetype, SetupV2Qualification

        variant = SetupV2Variant(
            SetupV2Archetype.NEXT_BAR,
            SetupV2Qualification.LEGACY_QUALIFIED,
            6,
        )
        self.assertEqual(variant.setup_bos_expiry_bars, 6)

    def test_strict_ordering(self):
        assert_strict_order(setup_bar=1, bos_bar=3, retest_bar=4, confirm_bar=5, entry_bar=6)

    def test_bos_retest_entry_window(self):
        self.assertEqual(RETRACE_WINDOW_BARS, 2)
        self.assertEqual(BOS_RETEST_TOLERANCE_ATR, 0.10)

    def test_frozen_execution_constants(self):
        cfg = frozen_sim_config()
        self.assertEqual(cfg.stop_atr, STOP_ATR)
        self.assertEqual(cfg.target_r, TARGET_R)
        self.assertEqual(cfg.max_bars, MAX_HOLD_BARS)
        self.assertEqual(cfg.management, "FIXED")

    def test_ambiguous_bar_stop_first(self):
        tz = "America/Chicago"
        index = pd.date_range("2026-01-02 09:30", periods=4, freq="15min", tz=tz)
        market = pd.DataFrame(
            {
                "open": [100.0, 100.0, 100.0, 100.0],
                "high": [100.5, 100.5, 105.0, 100.5],
                "low": [99.5, 99.5, 95.0, 99.5],
                "close": [100.0, 100.0, 100.0, 100.0],
                "atr": [2.0, 2.0, 2.0, 2.0],
            },
            index=index,
        )
        pos_map = {ts: i for i, ts in enumerate(market.index)}
        engine = TradeEngine(FrozenConfig(chart_minutes=15, trade_stop_atr=0.75, trade_target_r=3.0))
        from phase16.models import EntryEvent

        event = EntryEvent(
            model="Confirm",
            direction=1,
            score=80.0,
            entry_timestamp=index[1],
            setup_timestamp=index[0],
            bos_timestamp=index[0],
            retest_timestamp=index[0],
            confirm_timestamp=index[1],
            htf_regime=1,
            session_bucket=2,
        )
        engine.try_open(event, bar_index=1, close=100.0, atr=2.0)
        engine.manage_bar(
            bar_index=2,
            timestamp=index[2],
            bar_end=index[2] + pd.Timedelta(minutes=15),
            high=105.0,
            low=95.0,
            close=100.0,
            end_exclusive=index[-1] + pd.Timedelta(minutes=30),
        )
        self.assertEqual(len(engine.completed), 1)
        self.assertEqual(engine.completed[0].exit_reason, "STOP")

    def test_parity_reference_builds(self):
        reference, windows, perf = build_parity_reference()
        self.assertGreater(len(reference), 0)
        self.assertGreater(len(windows), 0)
        self.assertIn("net_AvgR", perf)
        self.assertTrue(reference["setup_timestamp"].le(reference["bos_timestamp"]).all())
        self.assertTrue(reference["bos_timestamp"].le(reference["retest_timestamp"]).all())
        self.assertTrue(reference["retest_timestamp"].le(reference["confirm_timestamp"]).all())
        self.assertTrue(reference["confirm_timestamp"].lt(reference["entry_timestamp"]).all())


if __name__ == "__main__":
    unittest.main()
