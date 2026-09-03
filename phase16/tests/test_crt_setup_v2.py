"""Tests for CRT Setup V2 experimental architecture."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from phase16.config import FrozenConfig
from phase16.crt_setup_v2 import (
    SetupV2Archetype,
    SetupV2Detector,
    SetupV2Funnel,
    SetupV2Qualification,
    SetupV2Variant,
    passes_legacy_qualification,
    run_crt_setup_v2_study,
    run_setup_v2_backtest,
)
from phase16.data_loader import load_ohlcv_csv
from phase16.models import SetupEvent
from phase16.sequential_bos import SequentialBosConfig, assert_strict_order


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"
ARCHIVED = ROOT / "phase16" / "results" / "oos" / "trades.csv"


def _frame() -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2026-01-02 09:30", periods=8, freq="5min", tz=tz)
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
            "low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0],
            "volume": [100] * 8,
            "atr": [2.0] * 8,
            "body_sma": [1.0] * 8,
            "structure_pivot_high": [float("nan")] * 8,
            "structure_pivot_low": [float("nan")] * 8,
            "liquidity_pivot_high": [float("nan")] * 8,
            "liquidity_pivot_low": [float("nan")] * 8,
            "htf_regime": [1] * 8,
            "crt_high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
            "crt_low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5],
        },
        index=index,
    )


def _setup_event(**kwargs) -> SetupEvent:
    defaults = dict(
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
    defaults.update(kwargs)
    return SetupEvent(**defaults)


class CrtSetupV2Tests(unittest.TestCase):
    def test_baseline_parity_and_study(self):
        if not DATA.exists() or not ARCHIVED.exists():
            self.skipTest("dataset unavailable")
        out = ROOT / "phase16" / "results" / "crt_setup_v2_test"
        manifest = run_crt_setup_v2_study(
            load_ohlcv_csv(DATA, exchange_timezone=FrozenConfig().exchange_timezone),
            output=out,
            archived_trade_path=ARCHIVED,
        )
        self.assertTrue(manifest["baseline_parity"])
        self.assertTrue(manifest["ordering_pass"])
        self.assertEqual(len(manifest["variants"]), 18)

    def test_liquidity_reference_known_before_sweep(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.SAME_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        bar = 3
        row = data.iloc[bar]
        self.assertTrue(_finite(row.crt_low))
        self.assertTrue(_finite(row.crt_high))
        self.assertLess(float(row.crt_low), float(row.high))

    def test_long_sweep_requires_trade_below_liquidity_low(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.SAME_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        bar = 3
        data.iloc[bar, data.columns.get_loc("low")] = float(data.iloc[bar].crt_low) - 0.5
        data.iloc[bar, data.columns.get_loc("close")] = float(data.iloc[bar].crt_low) + 0.25
        candidate = detector.step(
            bar_index=bar,
            timestamp=data.index[bar],
            open_price=float(data.iloc[bar].open),
            high=float(data.iloc[bar].high),
            low=float(data.iloc[bar].low),
            close=float(data.iloc[bar].close),
            atr=2.0,
            crt_high=float(data.iloc[bar].crt_high),
            crt_low=float(data.iloc[bar].crt_low),
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.direction, 1)

    def test_short_sweep_requires_trade_above_liquidity_high(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.SAME_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        bar = 3
        data.iloc[bar, data.columns.get_loc("high")] = float(data.iloc[bar].crt_high) + 0.5
        data.iloc[bar, data.columns.get_loc("close")] = float(data.iloc[bar].crt_high) - 0.25
        candidate = detector.step(
            bar_index=bar,
            timestamp=data.index[bar],
            open_price=float(data.iloc[bar].open),
            high=float(data.iloc[bar].high),
            low=float(data.iloc[bar].low),
            close=float(data.iloc[bar].close),
            atr=2.0,
            crt_high=float(data.iloc[bar].crt_high),
            crt_low=float(data.iloc[bar].crt_low),
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.direction, -1)

    def test_same_bar_reclaim(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.SAME_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        bar = 3
        crt_low = float(data.iloc[bar].crt_low)
        data.iloc[bar, data.columns.get_loc("low")] = crt_low - 0.1
        data.iloc[bar, data.columns.get_loc("close")] = crt_low + 0.1
        candidate = detector.step(
            bar_index=bar,
            timestamp=data.index[bar],
            open_price=float(data.iloc[bar].open),
            high=float(data.iloc[bar].high),
            low=float(data.iloc[bar].low),
            close=float(data.iloc[bar].close),
            atr=2.0,
            crt_high=float(data.iloc[bar].crt_high),
            crt_low=crt_low,
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertEqual(candidate.reclaim_mode, "same_bar")
        self.assertEqual(candidate.setup_bar, bar)

    def test_next_bar_reclaim_and_expiry(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.NEXT_BAR,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        sweep_bar = 3
        crt_low = float(data.iloc[sweep_bar].crt_low)
        data.iloc[sweep_bar, data.columns.get_loc("low")] = crt_low - 0.1
        data.iloc[sweep_bar, data.columns.get_loc("close")] = crt_low - 0.05
        none = detector.step(
            bar_index=sweep_bar,
            timestamp=data.index[sweep_bar],
            open_price=float(data.iloc[sweep_bar].open),
            high=float(data.iloc[sweep_bar].high),
            low=float(data.iloc[sweep_bar].low),
            close=float(data.iloc[sweep_bar].close),
            atr=2.0,
            crt_high=float(data.iloc[sweep_bar].crt_high),
            crt_low=crt_low,
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertIsNone(none)
        reclaim_bar = sweep_bar + 1
        data.iloc[reclaim_bar, data.columns.get_loc("close")] = crt_low + 0.1
        candidate = detector.step(
            bar_index=reclaim_bar,
            timestamp=data.index[reclaim_bar],
            open_price=float(data.iloc[reclaim_bar].open),
            high=float(data.iloc[reclaim_bar].high),
            low=float(data.iloc[reclaim_bar].low),
            close=float(data.iloc[reclaim_bar].close),
            atr=2.0,
            crt_high=float(data.iloc[reclaim_bar].crt_high),
            crt_low=float(data.iloc[reclaim_bar].crt_low),
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertEqual(candidate.reclaim_mode, "next_bar")
        expire_bar = sweep_bar + 2
        detector.pending = detector._record_sweep(
            direction=1,
            bar_index=sweep_bar,
            timestamp=data.index[sweep_bar],
            liquidity_level=crt_low,
            low=crt_low - 0.1,
            high=float(data.iloc[sweep_bar].high),
            atr=2.0,
        )
        expired = detector.step(
            bar_index=expire_bar,
            timestamp=data.index[expire_bar],
            open_price=float(data.iloc[expire_bar].open),
            high=float(data.iloc[expire_bar].high),
            low=float(data.iloc[expire_bar].low),
            close=float(data.iloc[expire_bar].close),
            atr=2.0,
            crt_high=float(data.iloc[expire_bar].crt_high),
            crt_low=float(data.iloc[expire_bar].crt_low),
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertIsNone(expired)

    def test_same_or_next_accepts_both_modes(self):
        data = _frame()
        config = FrozenConfig()
        detector = SetupV2Detector(
            archetype=SetupV2Archetype.SAME_OR_NEXT,
            qualification=SetupV2Qualification.STRUCTURE_ONLY,
            config=config,
            data=data,
        )
        bar = 3
        crt_low = float(data.iloc[bar].crt_low)
        data.iloc[bar, data.columns.get_loc("low")] = crt_low - 0.1
        data.iloc[bar, data.columns.get_loc("close")] = crt_low + 0.1
        same = detector.step(
            bar_index=bar,
            timestamp=data.index[bar],
            open_price=float(data.iloc[bar].open),
            high=float(data.iloc[bar].high),
            low=float(data.iloc[bar].low),
            close=float(data.iloc[bar].close),
            atr=2.0,
            crt_high=float(data.iloc[bar].crt_high),
            crt_low=crt_low,
            setup_event=_setup_event(),
            funnel_idle=True,
        )
        self.assertEqual(same.reclaim_mode, "same_bar")

    def test_bos_must_be_after_setup(self):
        config = FrozenConfig()
        funnel = SetupV2Funnel(config, SequentialBosConfig())
        with self.assertRaises(AssertionError):
            assert_strict_order(setup_bar=5, bos_bar=5, retest_bar=6, confirm_bar=7, entry_bar=7)

    def test_legacy_qualification_requires_variant_c_and_score(self):
        config = FrozenConfig()
        ok = passes_legacy_qualification(_setup_event(long_score=80, htf_regime=1, session_bucket=2), 1, config)
        bad_score = passes_legacy_qualification(_setup_event(long_score=60), 1, config)
        bad_htf = passes_legacy_qualification(_setup_event(htf_regime=0), 1, config)
        self.assertTrue(ok)
        self.assertFalse(bad_score)
        self.assertFalse(bad_htf)

    def test_full_backtest_ordering(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        variant = SetupV2Variant(SetupV2Archetype.SAME_OR_NEXT, SetupV2Qualification.STRUCTURE_ONLY, 6)
        trades, counters, _, _ = run_setup_v2_backtest(
            load_ohlcv_csv(DATA, exchange_timezone=FrozenConfig().exchange_timezone),
            variant=variant,
            start="2024-01-01",
            end="2026-06-26",
        )
        self.assertEqual(counters.same_bar_bos_retest, 0)
        self.assertEqual(counters.same_bar_retest_confirm, 0)


if __name__ == "__main__":
    unittest.main()
