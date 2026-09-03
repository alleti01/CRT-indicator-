"""Regression tests for the experimental SEQUENTIAL_BOS architecture."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from phase16.backtest import run_backtest
from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.entry_models import EntryFunnel
from phase16.models import SetupEvent, StructureEvent
from phase16.sequential_bos import (
    BosDefinition,
    SequentialBosConfig,
    SequentialBosFunnel,
    assert_strict_order,
    run_comparison_study,
    run_sequential_bos_backtest,
    summarize_architecture,
    verify_completed_trade_ordering,
    verify_retest_gated_parity,
)


ROOT = Path(__file__).resolve().parents[2]
ARCHIVED = ROOT / "phase16" / "results" / "oos" / "trades.csv"
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"
PINE_FROZEN = ROOT / "outputs" / "CRT_Core_RETEST_GATED_LIVE.pine"


class SequentialBosTests(unittest.TestCase):
    def setUp(self):
        self.config = FrozenConfig()
        self.start = pd.Timestamp("2026-07-01 10:00", tz=self.config.exchange_timezone)

    def setup(self, direction: int = 0) -> SetupEvent:
        return SetupEvent(
            canonical_long=direction == 1,
            canonical_short=direction == -1,
            canonical_score=90 if direction else 0,
            htf_regime=1 if direction == 1 else -1 if direction == -1 else 0,
            session_bucket=2,
        )

    def structure(self, bull: bool = False, bear: bool = False) -> StructureEvent:
        return StructureEvent(
            bull_bos=bull,
            bear_bos=bear,
            previous_active_high=100.0,
            previous_active_low=100.0,
            active_high=101.0,
            active_low=99.0,
        )

    def empty_swings(self):
        return (None, None), (None, None)

    def step_seq(
        self,
        funnel: SequentialBosFunnel,
        bar: int,
        *,
        direction: int = 0,
        bull: bool = False,
        bear: bool = False,
        open_price: float = 100.0,
        high: float = 101.0,
        low: float = 99.0,
        close: float = 100.0,
    ):
        swings = self.empty_swings()
        return funnel.step(
            bar_index=bar,
            timestamp=self.start + pd.Timedelta(minutes=5 * bar),
            open_price=open_price,
            high=high,
            low=low,
            close=close,
            atr=1.0,
            setup=self.setup(direction),
            structure=self.structure(bull, bear),
            swing_22=swings[0],
            swing_33=swings[1],
        )

    def test_01_later_bos_retest_confirm_passes(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, direction=1)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.step_seq(funnel, 1, bull=True, close=101.0)
        self.assertEqual(funnel.state_name, "WAIT_RETEST")
        self.step_seq(funnel, 2, low=100.0, close=100.0)
        self.assertEqual(funnel.state_name, "WAIT_CONFIRM")
        confirm = self.step_seq(funnel, 3, open_price=100.0, close=101.0)
        self.assertEqual([event.model for event in confirm], ["Confirm"])

    def test_02_same_bar_setup_bos_is_invalidated(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 10, direction=-1, bear=True, close=99.0)
        self.assertEqual(funnel.state_name, "IDLE")
        self.assertEqual(funnel.counters.same_bar_setup_bos, 1)

    def test_03_bos_before_setup_is_not_reused(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, bull=True)
        self.step_seq(funnel, 1, direction=1)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.assertEqual(funnel.bos_bar, -1)

    def test_04_bos_retest_cannot_share_bar(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, direction=1)
        self.step_seq(funnel, 1, bull=True, close=101.0)
        self.step_seq(funnel, 1, low=100.0, close=101.0)
        self.assertEqual(funnel.state_name, "IDLE")
        self.assertEqual(funnel.counters.same_bar_bos_retest, 1)

    def test_05_retest_confirm_cannot_share_bar(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, direction=1)
        self.step_seq(funnel, 1, bull=True, close=101.0)
        self.step_seq(funnel, 2, low=100.0, close=100.0)
        self.step_seq(funnel, 2, open_price=100.0, close=101.0)
        self.assertEqual(funnel.state_name, "IDLE")
        self.assertEqual(funnel.counters.same_bar_retest_confirm, 1)

    def test_06_new_same_direction_bos_after_setup_qualifies(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, direction=1)
        self.step_seq(funnel, 2, bull=True, close=101.0)
        self.assertEqual(funnel.state_name, "WAIT_RETEST")

    def test_07_opposite_bos_invalidates(self):
        funnel = SequentialBosFunnel(self.config, SequentialBosConfig())
        self.step_seq(funnel, 0, direction=1)
        self.step_seq(funnel, 1, bear=True)
        self.assertEqual(funnel.state_name, "IDLE")

    def test_08_setup_bos_expiry_resets(self):
        funnel = SequentialBosFunnel(
            self.config, SequentialBosConfig(setup_bos_expiry_bars=3)
        )
        self.step_seq(funnel, 0, direction=1)
        self.step_seq(funnel, 4)
        self.assertEqual(funnel.state_name, "IDLE")

    def test_09_retest_gated_parity_with_frozen_baseline(self):
        if not DATA.exists() or not ARCHIVED.exists():
            self.skipTest("full dataset or archived trades unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        result = run_backtest(data, start="2024-01-01", end="2026-06-26", config=self.config)
        verify_retest_gated_parity(result.trades, ARCHIVED)

    def test_10_original_mode_source_is_unchanged(self):
        source = PINE_FROZEN.read_text()
        start = "// Original mode preserves the prior immediate-entry semantics exactly."
        end = "// Retest-gated official state changes only on a CLOSED candle"
        block = source[source.index(start) : source.index(end)]
        self.assertIn("if processBar and not liveRetestMode", block)
        self.assertNotIn("Sequential-BOS", block)

    def test_11_debug_flag_does_not_change_trades(self):
        if not DATA.exists():
            self.skipTest("processed data unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        base, _ = run_sequential_bos_backtest(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=self.config,
            seq_config=SequentialBosConfig(debug_events=False),
        )
        debug, _ = run_sequential_bos_backtest(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=self.config,
            seq_config=SequentialBosConfig(debug_events=True),
        )
        pd.testing.assert_frame_equal(
            base.trades.reset_index(drop=True),
            debug.trades.reset_index(drop=True),
        )

    def test_12_strict_order_assertion(self):
        assert_strict_order(setup_bar=1, bos_bar=2, retest_bar=3, confirm_bar=4, entry_bar=4)
        with self.assertRaises(AssertionError):
            assert_strict_order(setup_bar=1, bos_bar=1, retest_bar=2, confirm_bar=3, entry_bar=3)

    def test_13_retest_gated_allows_same_bar_setup_bos(self):
        funnel = EntryFunnel(self.config)
        events = funnel.step(
            bar_index=10,
            timestamp=self.start,
            open_price=100.0,
            high=101.0,
            low=99.0,
            close=99.0,
            atr=1.0,
            setup=self.setup(-1),
            structure=self.structure(bear=True),
        )
        self.assertIn("BOS", [event.model for event in events])
        self.assertEqual(funnel.setup_bar, funnel.bos_bar)

    def test_14_full_study_has_zero_same_bar_violations(self):
        if not DATA.exists() or not ARCHIVED.exists():
            self.skipTest("full dataset or archived trades unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        output = ROOT / "phase16" / "results" / "sequential_bos_test"
        manifest = run_comparison_study(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=self.config,
            archived_trade_path=ARCHIVED,
            output=output,
        )
        funnels = pd.read_csv(output / "funnel_report.csv")
        comparison = pd.read_csv(output / "architecture_comparison.csv")
        seq_rows = comparison.loc[comparison.architecture == "SEQUENTIAL_BOS"]
        for _, trade_file in seq_rows.iterrows():
            trades = pd.read_csv(
                output / f"trades_{trade_file.bos_definition}_{int(trade_file.setup_bos_expiry_bars)}.csv"
            )
            if trades.empty:
                continue
            verify_completed_trade_ordering(
                trades,
                data_index=load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone).index,
            )
        self.assertEqual(
            summarize_architecture(
                run_backtest(data, start="2024-01-01", end="2026-06-26", config=self.config)
                .trades.loc[lambda df: df.model == "Confirm"]
            )["N"],
            705,
        )
        self.assertIn("classification", manifest)


if __name__ == "__main__":
    unittest.main()
