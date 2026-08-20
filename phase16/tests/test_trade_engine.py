import unittest

import pandas as pd

from phase16.config import FrozenConfig
from phase16.models import EntryEvent
from phase16.trade_engine import TradeEngine


class TradeEngineTests(unittest.TestCase):
    def setUp(self):
        self.config = FrozenConfig()
        self.timestamp = pd.Timestamp("2026-07-01 10:00", tz=self.config.exchange_timezone)
        self.event = EntryEvent(
            model="Control",
            direction=1,
            score=85,
            entry_timestamp=self.timestamp,
            setup_timestamp=self.timestamp,
            htf_regime=1,
            session_bucket=2,
        )

    def test_stop_first_when_stop_and_target_touch(self):
        engine = TradeEngine(self.config)
        engine.try_open(self.event, bar_index=0, close=100, atr=1)
        engine.manage_bar(
            bar_index=1,
            timestamp=self.timestamp + pd.Timedelta(5, unit="m"),
            bar_end=self.timestamp + pd.Timedelta(10, unit="m"),
            high=104,
            low=98,
            close=101,
            end_exclusive=self.timestamp + pd.Timedelta(1, unit="D"),
        )
        self.assertEqual(engine.completed[0].result_R, -1.0)
        self.assertEqual(engine.completed[0].exit_reason, "STOP")

    def test_one_active_trade_per_model(self):
        engine = TradeEngine(self.config)
        self.assertTrue(engine.try_open(self.event, bar_index=0, close=100, atr=1))
        self.assertFalse(engine.try_open(self.event, bar_index=1, close=101, atr=1))
        self.assertEqual(engine.accepted["Control"], 1)
        self.assertEqual(engine.attempts["Control"], 2)


if __name__ == "__main__":
    unittest.main()
