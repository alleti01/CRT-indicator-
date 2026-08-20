import unittest

import pandas as pd

from phase16.config import FrozenConfig
from phase16.entry_models import EntryFunnel
from phase16.models import SetupEvent, StructureEvent


class FunnelTests(unittest.TestCase):
    def setUp(self):
        self.config = FrozenConfig()
        self.base = pd.Timestamp("2026-07-01 10:00", tz=self.config.exchange_timezone)

    def _setup(self, canonical=True):
        return SetupEvent(
            canonical_long=canonical,
            canonical_score=85,
            htf_regime=1,
            session_bucket=2,
        )

    def test_retest_and_confirm_require_later_bars(self):
        funnel = EntryFunnel(self.config)
        bos_structure = StructureEvent(
            bull_bos=True,
            previous_active_high=100.0,
            active_high=105.0,
        )
        first = funnel.step(
            bar_index=10,
            timestamp=self.base,
            open_price=100,
            high=102,
            low=99,
            close=101,
            atr=2,
            setup=self._setup(),
            structure=bos_structure,
        )
        self.assertEqual([event.model for event in first], ["Control", "BOS"])
        self.assertEqual(funnel.state_name, "WAIT_RETEST")

        retest = funnel.step(
            bar_index=11,
            timestamp=self.base + pd.Timedelta(5, unit="m"),
            open_price=100.5,
            high=101,
            low=100.1,
            close=100.3,
            atr=2,
            setup=self._setup(False),
            structure=StructureEvent(),
        )
        self.assertEqual([event.model for event in retest], ["Retest"])
        self.assertEqual(funnel.state_name, "WAIT_CONFIRM")

        confirmation = funnel.step(
            bar_index=12,
            timestamp=self.base + pd.Timedelta(10, unit="m"),
            open_price=100.2,
            high=101.5,
            low=100.1,
            close=101.0,
            atr=2,
            setup=self._setup(False),
            structure=StructureEvent(),
        )
        self.assertEqual([event.model for event in confirmation], ["Confirm"])
        self.assertEqual(funnel.state_name, "IDLE")
        self.assertGreater(confirmation[0].confirm_timestamp, confirmation[0].retest_timestamp)

    def test_retest_cannot_occur_on_bos_bar(self):
        funnel = EntryFunnel(self.config)
        events = funnel.step(
            bar_index=1,
            timestamp=self.base,
            open_price=100,
            high=101,
            low=99,
            close=100.5,
            atr=1,
            setup=self._setup(),
            structure=StructureEvent(
                bull_bos=True, previous_active_high=100, active_high=101
            ),
        )
        self.assertNotIn("Retest", [event.model for event in events])


if __name__ == "__main__":
    unittest.main()
