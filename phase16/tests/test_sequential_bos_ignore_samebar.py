"""Tests for ignore-and-wait same-bar SEQUENTIAL_BOS experiment."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from phase16.backtest import run_backtest
from phase16.bos_semantic_audit import SwingBreak
from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.entry_models import EntryFunnel
from phase16.models import SetupEvent, StructureEvent
from phase16.sequential_bos import (
    BosDefinition,
    SequentialBosConfig,
    SequentialBosFunnel,
    run_sequential_bos_backtest,
    verify_retest_gated_parity,
    _summarize_with_costs,
)
from phase16.sequential_bos_ignore_samebar import (
    IgnoreSameBarFunnel,
    run_ignore_samebar_backtest,
    verify_control_parity,
)


ROOT = Path(__file__).resolve().parents[2]
ARCHIVED = ROOT / "phase16" / "results" / "oos" / "trades.csv"
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"


class IgnoreSameBarTests(unittest.TestCase):
    def setUp(self):
        self.config = FrozenConfig()
        self.start = pd.Timestamp("2026-07-01 10:00", tz=self.config.exchange_timezone)
        self.seq = SequentialBosConfig(
            bos_definition=BosDefinition.SWING_2_2,
            setup_bos_expiry_bars=3,
        )

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

    def swing_break(self, *, bar: int, direction: int, level: float) -> SwingBreak:
        ts = self.start + pd.Timedelta(minutes=5 * bar)
        return SwingBreak(
            direction=direction,
            bar_index=bar,
            timestamp=ts,
            level=level,
            pivot_bar=max(bar - 2, 0),
            pivot_timestamp=self.start,
            confirmation_bar=max(bar - 1, 0),
            confirmation_timestamp=self.start,
            bias_before=0,
            is_choch=False,
        )

    def step(
        self,
        funnel,
        bar: int,
        *,
        direction: int = 0,
        bull: bool = False,
        bear: bool = False,
        swing_22=(None, None),
        open_price: float = 100.0,
        high: float = 101.0,
        low: float = 99.0,
        close: float = 100.0,
    ):
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
            swing_22=swing_22,
            swing_33=(None, None),
        )

    def test_01_same_bar_event_does_not_invalidate_experiment(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=-1, bear=True, close=99.0)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.assertEqual(funnel.counters.same_bar_bos_ignored, 1)
        self.assertEqual(funnel.counters.same_bar_hard_invalidations, 0)

    def test_02_same_bar_event_does_not_qualify_as_bos(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=-1, bear=True, close=99.0)
        self.assertEqual(funnel.bos_bar, -1)

    def test_03_candidate_remains_wait_bos(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=1, bear=False, bull=True)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.step(funnel, 11)
        self.assertEqual(funnel.state_name, "WAIT_BOS")

    def test_04_genuinely_later_bos_qualifies(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        ignored = self.swing_break(bar=10, direction=1, level=100.5)
        later = self.swing_break(bar=11, direction=1, level=101.0)
        self.step(funnel, 10, direction=1, swing_22=(ignored, None), close=101.0)
        self.step(funnel, 11, swing_22=(later, None), close=101.5)
        self.assertEqual(funnel.state_name, "WAIT_RETEST")
        self.assertEqual(funnel.bos_bar, 11)

    def test_05_stale_setup_bar_event_cannot_qualify_later(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        ignored = self.swing_break(bar=10, direction=1, level=100.5)
        self.step(funnel, 10, direction=1, swing_22=(ignored, None), close=101.0)
        self.assertEqual(funnel.counters.same_bar_bos_ignored, 1)
        # No new swing event on next bar; boolean-like reuse must not advance BOS.
        self.step(funnel, 11, close=101.0)
        self.assertEqual(funnel.bos_bar, -1)
        later = self.swing_break(bar=12, direction=1, level=102.0)
        self.step(funnel, 12, swing_22=(later, None), close=102.5)
        self.assertEqual(funnel.bos_bar, 12)

    def test_06_opposite_structure_still_invalidates(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=1, bull=True)
        self.step(funnel, 11, bear=True)
        self.assertEqual(funnel.state_name, "IDLE")

    def test_07_expiry_still_works(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=1, bull=True)
        self.step(funnel, 14)
        self.assertEqual(funnel.state_name, "IDLE")

    def test_08_strict_ordering_still_works(self):
        funnel = IgnoreSameBarFunnel(self.config, self.seq)
        ignored = self.swing_break(bar=0, direction=1, level=100.5)
        bos = self.swing_break(bar=1, direction=1, level=101.0)
        self.step(funnel, 0, direction=1, swing_22=(ignored, None), close=101.0)
        self.step(funnel, 1, swing_22=(bos, None), close=101.5)
        self.step(funnel, 2, low=100.95, close=101.0)
        entries = self.step(funnel, 3, open_price=100.5, close=101.5)
        self.assertEqual([event.model for event in entries], ["Confirm"])

    def test_09_control_behavior_unchanged(self):
        funnel = SequentialBosFunnel(self.config, self.seq)
        self.step(funnel, 10, direction=-1, bear=True, close=99.0)
        self.assertEqual(funnel.state_name, "IDLE")
        self.assertEqual(funnel.counters.same_bar_setup_bos, 1)

    def test_10_retest_gated_parity_unchanged(self):
        if not DATA.exists() or not ARCHIVED.exists():
            self.skipTest("dataset unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        result = run_backtest(data, start="2024-01-01", end="2026-06-26", config=self.config)
        verify_retest_gated_parity(result.trades, ARCHIVED)

    def test_11_control_sequential_parity(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        result, counters = run_sequential_bos_backtest(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=self.config,
            seq_config=self.seq,
        )
        self.assertTrue(
            verify_control_parity(counters=counters, summary=_summarize_with_costs(result.trades))
        )

    def test_12_experiment_increases_recovered_setups(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        data = load_ohlcv_csv(DATA, exchange_timezone=self.config.exchange_timezone)
        _, experiment = run_ignore_samebar_backtest(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=self.config,
            seq_config=self.seq,
        )
        self.assertGreater(experiment.counters.recovered_setups, 1000)
        self.assertEqual(experiment.counters.same_bar_hard_invalidations, 0)
        self.assertEqual(experiment.counters.stale_setup_bar_bos_reuse, 0)


if __name__ == "__main__":
    unittest.main()
