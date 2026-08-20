import unittest

import numpy as np
import pandas as pd

from phase16.backtest import run_backtest
from phase16.config import FrozenConfig
from phase16.data_loader import normalize_ohlcv
from phase16.continuous import forward_adjust_rolls, select_provider_rolls
from phase16.resample import resample_ohlcv


class DataBacktestTests(unittest.TestCase):
    def setUp(self):
        self.config = FrozenConfig()

    def test_alternate_columns_and_resampling(self):
        timestamps = pd.date_range(
            "2026-07-01 09:30", periods=10, freq="1min", tz=self.config.exchange_timezone
        )
        raw = pd.DataFrame(
            {
                "datetime": timestamps,
                "O": np.arange(10, dtype=float) + 100,
                "H": np.arange(10, dtype=float) + 101,
                "L": np.arange(10, dtype=float) + 99,
                "C": np.arange(10, dtype=float) + 100.5,
                "V": np.ones(10),
            }
        )
        normalized = normalize_ohlcv(raw, exchange_timezone=self.config.exchange_timezone)
        bars = resample_ohlcv(normalized, 5)
        self.assertEqual(len(bars), 2)
        self.assertEqual(bars.iloc[0]["open"], 100)
        self.assertEqual(bars.iloc[0]["high"], 105)
        self.assertEqual(bars.iloc[0]["low"], 99)
        self.assertEqual(bars.iloc[0]["close"], 104.5)
        self.assertEqual(bars.iloc[0]["volume"], 5)

    def test_date_filtering_is_inclusive_by_exchange_date(self):
        index = pd.date_range(
            "2026-06-28 23:50", periods=8, freq="5min", tz=self.config.exchange_timezone
        )
        prices = np.arange(len(index), dtype=float) + 100
        frame = pd.DataFrame(
            {
                "open": prices,
                "high": prices + 1,
                "low": prices - 1,
                "close": prices + 0.25,
                "volume": 1,
            },
            index=index,
        )
        result = run_backtest(
            frame,
            start="2026-06-29",
            end="2026-06-29",
            config=self.config,
        )
        self.assertEqual(result.diagnostics["Bars In Window"], 6)
        self.assertEqual(result.coverage, "PARTIAL DATA")

    def test_provider_roll_gap_is_removed(self):
        index = pd.date_range(
            "2026-06-16 18:58", periods=4, freq="1min", tz=self.config.exchange_timezone
        )
        frame = pd.DataFrame(
            {
                "open": [100.0, 101.0, 120.0, 121.0],
                "high": [101.0, 102.0, 121.0, 122.0],
                "low": [99.0, 100.0, 119.0, 120.0],
                "close": [100.5, 101.5, 120.5, 121.5],
                "volume": [1, 1, 1, 1],
                "instrument_id": [1, 1, 2, 2],
            },
            index=index,
        )
        selected = select_provider_rolls(frame)
        adjusted = forward_adjust_rolls(selected)
        self.assertEqual(adjusted.iloc[2]["open"], adjusted.iloc[1]["close"])
        self.assertEqual(adjusted.iloc[3]["close"] - adjusted.iloc[2]["close"], 1.0)


if __name__ == "__main__":
    unittest.main()
