import unittest

import numpy as np
import pandas as pd

from phase16.bos_semantic_audit import CausalSwingEngine, StructuralFunnel, SwingBreak
from phase16.config import FrozenConfig
from phase16.models import SetupEvent


class BOSSemanticAuditTests(unittest.TestCase):
    def test_pivot_is_usable_only_after_confirmation_bar(self) -> None:
        index = pd.date_range("2024-01-01", periods=8, freq="5min", tz="America/Chicago")
        engine = CausalSwingEngine(2, 2)
        # Pivot at bar 2 is first known/emitted at bar 4.
        for bar in range(4):
            bull, _, _ = engine.step(
                bar_index=bar,
                timestamp=index[bar],
                index=index,
                close=9.0,
                pivot_high=np.nan,
                pivot_low=np.nan,
            )
            self.assertIsNone(bull)
        bull, _, _ = engine.step(
            bar_index=4,
            timestamp=index[4],
            index=index,
            close=11.0,
            pivot_high=10.0,
            pivot_low=np.nan,
        )
        self.assertIsNone(bull, "break-before-pivot ordering must reject a same-confirmation-bar break")
        bull, _, _ = engine.step(
            bar_index=5,
            timestamp=index[5],
            index=index,
            close=11.0,
            pivot_high=np.nan,
            pivot_low=np.nan,
        )
        self.assertIsNotNone(bull)
        assert bull is not None
        self.assertEqual(bull.pivot_bar, 2)
        self.assertEqual(bull.confirmation_bar, 4)

    def test_structural_counterfactual_forbids_same_bar_bos(self) -> None:
        config = FrozenConfig()
        funnel = StructuralFunnel(config)
        timestamp = pd.Timestamp("2024-01-02 09:30", tz=config.exchange_timezone)
        setup = SetupEvent(canonical_long=True, canonical_score=85, htf_regime=1, session_bucket=2)
        event = SwingBreak(1, 10, timestamp, 100.0, 5, timestamp, 7, timestamp, 0, False)
        entry = funnel.step(
            bar_index=10,
            timestamp=timestamp,
            open_price=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            atr=2.0,
            setup=setup,
            bull_break=event,
            bear_break=None,
        )
        self.assertIsNone(entry)
        self.assertEqual(funnel.state, 1)

    def test_structural_counterfactual_preserves_same_bar_opposite_invalidation(self) -> None:
        config = FrozenConfig()
        funnel = StructuralFunnel(config)
        timestamp = pd.Timestamp("2024-01-02 09:30", tz=config.exchange_timezone)
        setup = SetupEvent(canonical_long=True, canonical_score=85, htf_regime=1, session_bucket=2)
        opposite = SwingBreak(-1, 10, timestamp, 99.0, 5, timestamp, 7, timestamp, 0, False)
        entry = funnel.step(
            bar_index=10,
            timestamp=timestamp,
            open_price=100.0,
            high=101.0,
            low=98.0,
            close=99.0,
            atr=2.0,
            setup=setup,
            bull_break=None,
            bear_break=opposite,
        )
        self.assertIsNone(entry)
        self.assertEqual(funnel.state, 0)


if __name__ == "__main__":
    unittest.main()
