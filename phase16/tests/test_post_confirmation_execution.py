"""Tests for post-confirmation entry execution study."""

from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.post_confirmation_execution import (
    LIMIT_WINDOW,
    apply_execution_costs,
    resolve_execution_model,
    run_post_confirmation_execution_study,
    simulate_execution_trade,
)


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"


def _synthetic_data() -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2026-01-02 09:30", periods=12, freq="5min", tz=tz)
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0],
            "high": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5, 111.5],
            "low": [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5, 108.5, 109.5, 110.5],
            "close": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0],
            "volume": [100] * 12,
            "atr": [2.0] * 12,
        },
        index=index,
    )


class PostConfirmationExecutionTests(unittest.TestCase):
    def test_reproduction_on_dataset(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        config = FrozenConfig()
        data = load_ohlcv_csv(DATA, exchange_timezone=config.exchange_timezone)
        out = ROOT / "phase16" / "results" / "post_confirmation_execution_test"
        manifest = run_post_confirmation_execution_study(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=config,
            output=out,
        )
        self.assertTrue(manifest["reproduced"])
        self.assertEqual(manifest["baseline"]["N"], 54)
        self.assertAlmostEqual(manifest["baseline"]["net_TotalR"], -0.93, delta=0.2)

    def test_next_bar_cannot_execute_on_confirm_bar(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        resolution = resolve_execution_model(
            "NEXT_BAR_OPEN",
            data=data,
            confirm_bar=3,
            retest_bar=2,
            bos_level=101.5,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(resolution.filled)
        self.assertEqual(resolution.entry_bar, 4)
        self.assertEqual(resolution.entry_price, float(data.iloc[4].open))

    def test_limit_cannot_fill_before_or_on_confirm_bar(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        confirm_bar = 3
        limit = (float(data.iloc[confirm_bar].high) + float(data.iloc[confirm_bar].low)) / 2.0
        for model in ("CONFIRM_MIDPOINT_50", "BOS_LEVEL_PULLBACK", "RETEST_CLOSE"):
            resolution = resolve_execution_model(
                model,
                data=data,
                confirm_bar=confirm_bar,
                retest_bar=2,
                bos_level=101.5,
                direction=1,
                end_exclusive=end,
                config=config,
            )
            if resolution.filled:
                self.assertGreater(resolution.entry_bar, confirm_bar)

        # Force a midpoint that would have touched confirm bar low but must wait.
        data.iloc[4, data.columns.get_loc("low")] = limit - 0.1
        resolution = resolve_execution_model(
            "CONFIRM_MIDPOINT_50",
            data=data,
            confirm_bar=confirm_bar,
            retest_bar=2,
            bos_level=101.5,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(resolution.filled)
        self.assertEqual(resolution.entry_bar, 4)

    def test_three_bar_expiry(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        resolution = resolve_execution_model(
            "BOS_LEVEL_PULLBACK",
            data=data,
            confirm_bar=3,
            retest_bar=2,
            bos_level=95.0,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertFalse(resolution.filled)
        self.assertEqual(resolution.cancel_reason, "limit_not_filled_3_bars")
        self.assertEqual(resolution.bars_waited, LIMIT_WINDOW)

    def test_long_midpoint_fill(self):
        config = FrozenConfig()
        data = _synthetic_data()
        confirm_bar = 3
        midpoint = (float(data.iloc[confirm_bar].high) + float(data.iloc[confirm_bar].low)) / 2.0
        data.iloc[5, data.columns.get_loc("low")] = midpoint - 0.01
        end = data.index[-1] + pd.Timedelta(days=1)
        resolution = resolve_execution_model(
            "CONFIRM_MIDPOINT_50",
            data=data,
            confirm_bar=confirm_bar,
            retest_bar=2,
            bos_level=101.0,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(resolution.filled)
        self.assertEqual(resolution.entry_bar, 5)
        self.assertAlmostEqual(resolution.entry_price, midpoint)

    def test_short_midpoint_fill(self):
        config = FrozenConfig()
        data = _synthetic_data()
        confirm_bar = 3
        midpoint = (float(data.iloc[confirm_bar].high) + float(data.iloc[confirm_bar].low)) / 2.0
        data.iloc[4, data.columns.get_loc("high")] = midpoint - 0.01
        data.iloc[5, data.columns.get_loc("high")] = midpoint + 0.01
        end = data.index[-1] + pd.Timedelta(days=1)
        resolution = resolve_execution_model(
            "CONFIRM_MIDPOINT_50",
            data=data,
            confirm_bar=confirm_bar,
            retest_bar=2,
            bos_level=105.0,
            direction=-1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(resolution.filled)
        self.assertEqual(resolution.entry_bar, 5)
        self.assertAlmostEqual(resolution.entry_price, midpoint)

    def test_bos_and_retest_close_fill(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        bos_level = 101.5
        data.iloc[4, data.columns.get_loc("low")] = bos_level - 0.01
        bos = resolve_execution_model(
            "BOS_LEVEL_PULLBACK",
            data=data,
            confirm_bar=3,
            retest_bar=2,
            bos_level=bos_level,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(bos.filled)
        self.assertAlmostEqual(bos.entry_price, bos_level)

        retest_close = float(data.iloc[2].close)
        data.iloc[4, data.columns.get_loc("low")] = retest_close - 0.01
        retest = resolve_execution_model(
            "RETEST_CLOSE",
            data=data,
            confirm_bar=3,
            retest_bar=2,
            bos_level=bos_level,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertTrue(retest.filled)
        self.assertAlmostEqual(retest.entry_price, retest_close)

    def test_conservative_ambiguous_bar_stop_first(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        entry_bar = 4
        entry_price = 103.0
        stop = 102.0
        target = 106.0
        data.iloc[entry_bar, data.columns.get_loc("low")] = 101.5
        data.iloc[entry_bar, data.columns.get_loc("high")] = 107.0
        trade = simulate_execution_trade(
            data,
            entry_bar=entry_bar,
            entry_price=entry_price,
            direction=1,
            stop_price=stop,
            target_price=target,
            risk_points=1.0,
            config=config,
            end_exclusive=end,
            check_entry_bar_exit=True,
        )
        self.assertIsNotNone(trade)
        self.assertEqual(trade["gross_R"], -1.0)
        self.assertEqual(trade["exit_reason"], "STOP")

    def test_no_lookahead_current_uses_confirm_close(self):
        config = FrozenConfig()
        data = _synthetic_data()
        end = data.index[-1] + pd.Timedelta(days=1)
        confirm_bar = 3
        resolution = resolve_execution_model(
            "CURRENT",
            data=data,
            confirm_bar=confirm_bar,
            retest_bar=2,
            bos_level=101.0,
            direction=1,
            end_exclusive=end,
            config=config,
        )
        self.assertEqual(resolution.entry_bar, confirm_bar)
        self.assertEqual(resolution.entry_price, float(data.iloc[confirm_bar].close))

    def test_signal_ids_identical_across_models(self):
        if not DATA.exists():
            self.skipTest("dataset unavailable")
        config = FrozenConfig()
        data = load_ohlcv_csv(DATA, exchange_timezone=config.exchange_timezone)
        out = ROOT / "phase16" / "results" / "post_confirmation_execution_test"
        run_post_confirmation_execution_study(
            data,
            start="2024-01-01",
            end="2026-06-26",
            config=config,
            output=out,
        )
        trace = pd.read_csv(out / "execution_trade_trace.csv")
        signal_ids = trace.groupby("execution_model").signal_id.apply(lambda s: set(s)).to_dict()
        base = signal_ids["CURRENT"]
        for model, ids in signal_ids.items():
            self.assertEqual(base, ids)

    def test_reporting_does_not_alter_trades(self):
        trades = pd.DataFrame(
            [
                {
                    "entry_price": 100.0,
                    "stop_price": 97.0,
                    "gross_R": 1.0,
                    "direction": "Long",
                }
            ]
        )
        before = trades.copy()
        costed = apply_execution_costs(trades)
        self.assertEqual(float(before.gross_R.iloc[0]), 1.0)
        self.assertLess(float(costed.net_R.iloc[0]), 1.0)


if __name__ == "__main__":
    unittest.main()
