import unittest

import pandas as pd

from phase16.config import FrozenConfig
from phase16.models import LiquidityEvent, StructureEvent
from phase16.setup_engine import SetupEngine
from phase16.structure import StructureEngine


class StructureSetupTests(unittest.TestCase):
    def test_same_bar_double_break_is_skipped(self):
        engine = StructureEngine(FrozenConfig())
        engine.active_high = 101.0
        engine.active_low = 99.0
        event = engine.step(bar_index=10, high=103, low=97, close=100)
        # Close mode cannot double-break; exercise wick mode explicitly.
        wick_engine = StructureEngine(FrozenConfig(structure_break_mode="Wick"))
        wick_engine.active_high = 101.0
        wick_engine.active_low = 99.0
        wick_event = wick_engine.step(bar_index=10, high=103, low=97, close=100)
        self.assertFalse(wick_event.bull_bos)
        self.assertFalse(wick_event.bear_bos)

    def test_directional_cooldown(self):
        config = FrozenConfig(se_anti_chase=False)
        engine = SetupEngine(config)
        timestamp = pd.Timestamp("2026-07-01 10:00", tz=config.exchange_timezone)
        structure = StructureEvent(bull_bos=True, bias_before=0, bias_after=1)
        liquidity = LiquidityEvent(ssl_sweep=True)
        first = engine.step(
            bar_index=0,
            timestamp=timestamp,
            open_price=100,
            close=101,
            atr=1,
            body_average=10,
            htf_regime=1,
            structure=structure,
            liquidity=liquidity,
        )
        blocked = engine.step(
            bar_index=4,
            timestamp=timestamp,
            open_price=100,
            close=101,
            atr=1,
            body_average=10,
            htf_regime=1,
            structure=structure,
            liquidity=liquidity,
        )
        allowed = engine.step(
            bar_index=5,
            timestamp=timestamp,
            open_price=100,
            close=101,
            atr=1,
            body_average=10,
            htf_regime=1,
            structure=structure,
            liquidity=liquidity,
        )
        self.assertTrue(first.long_setup)
        self.assertFalse(blocked.long_setup)
        self.assertTrue(allowed.long_setup)


if __name__ == "__main__":
    unittest.main()

