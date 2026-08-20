"""Ordering regressions for the frozen Pine/Python entry funnel.

These tests validate event sequencing only. They do not tune or modify any
strategy parameter, setup rule, BOS rule, retest rule, or risk calculation.
"""

from pathlib import Path
import unittest

import pandas as pd

from phase16.config import FrozenConfig
from phase16.entry_models import EntryFunnel
from phase16.models import SetupEvent, StructureEvent


ROOT = Path(__file__).resolve().parents[2]
PINE_BEFORE = ROOT / "outputs" / "CRT_Core_RETEST_ENTRY_VISUAL_DEBUG.pine"
PINE_AFTER = ROOT / "outputs" / "CRT_Core_SAME_BAR_SETUP_BOS_DIAGNOSTIC.pine"


class SameBarSetupBosTests(unittest.TestCase):
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

    def step(
        self,
        funnel: EntryFunnel,
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
        )

    def test_01_later_bos_retest_confirm_passes(self):
        funnel = EntryFunnel(self.config)
        self.step(funnel, 0, direction=1)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        bos = self.step(funnel, 1, bull=True, close=101.0)
        self.assertIn("BOS", [event.model for event in bos])
        self.assertEqual(funnel.state_name, "WAIT_RETEST")
        retest = self.step(funnel, 2, low=100.0, close=100.0)
        self.assertIn("Retest", [event.model for event in retest])
        self.assertEqual(funnel.state_name, "WAIT_CONFIRM")
        confirm = self.step(funnel, 3, open_price=100.0, close=101.0)
        self.assertIn("Confirm", [event.model for event in confirm])

    def test_02_same_bar_setup_bos_passes(self):
        funnel = EntryFunnel(self.config)
        events = self.step(funnel, 10, direction=-1, bear=True, close=99.0)
        self.assertEqual([event.model for event in events], ["Control", "BOS"])
        self.assertEqual(funnel.setup_bar, funnel.bos_bar)
        self.assertEqual(funnel.state_name, "WAIT_RETEST")

    def test_03_bos_before_setup_is_not_reused(self):
        funnel = EntryFunnel(self.config)
        self.step(funnel, 0, bull=True)
        self.step(funnel, 1, direction=1)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.assertEqual(funnel.bos_bar, -1)

    def test_04_setup_bos_retest_cannot_share_bar(self):
        funnel = EntryFunnel(self.config)
        events = self.step(funnel, 0, direction=1, bull=True, low=99.0, close=101.0)
        self.assertEqual([event.model for event in events], ["Control", "BOS"])
        self.assertNotIn("Retest", [event.model for event in events])
        self.assertEqual(funnel.state_name, "WAIT_RETEST")

    def test_05_retest_confirm_cannot_share_bar(self):
        funnel = EntryFunnel(self.config)
        self.step(funnel, 0, direction=1, bull=True, close=101.0)
        same_bar = self.step(
            funnel, 1, open_price=100.0, low=100.0, close=101.0
        )
        self.assertEqual([event.model for event in same_bar], ["Retest"])
        self.assertEqual(funnel.state_name, "WAIT_CONFIRM")
        later = self.step(funnel, 2, open_price=100.0, close=101.0)
        self.assertEqual([event.model for event in later], ["Confirm"])

    def test_06_long_setup_opposite_bos_does_not_arm(self):
        funnel = EntryFunnel(self.config)
        events = self.step(funnel, 0, direction=1, bear=True)
        self.assertNotIn("BOS", [event.model for event in events])
        self.assertNotEqual(funnel.state_name, "WAIT_RETEST")

    def test_07_short_setup_opposite_bos_does_not_arm(self):
        funnel = EntryFunnel(self.config)
        events = self.step(funnel, 0, direction=-1, bull=True)
        self.assertNotIn("BOS", [event.model for event in events])
        self.assertNotEqual(funnel.state_name, "WAIT_RETEST")

    def test_08_old_historical_bos_cannot_arm_new_setup(self):
        funnel = EntryFunnel(self.config)
        self.step(funnel, 0, bear=True)
        self.step(funnel, 15, direction=-1)
        self.assertEqual(funnel.state_name, "WAIT_BOS")
        self.assertEqual(funnel.bos_bar, -1)

    def test_09_debug_switch_is_observability_only(self):
        source = PINE_AFTER.read_text()
        gate_start = source.index("liveAdvanceRetestGate(")
        gate_end = source.index("// Visualizes the exact stored BOS/retest level", gate_start)
        self.assertNotIn("showRetestDebug", source[gate_start:gate_end])
        for line in source.splitlines():
            if "showRetestDebug" not in line:
                continue
            self.assertTrue(
                any(
                    token in line
                    for token in (
                        "input.bool",
                        "liveUpdateRetestDebugLine",
                        "plotshape",
                        "dmShowLiveTable",
                        "gateTrace",
                    )
                ),
                line,
            )

    def test_10_original_mode_source_is_unchanged(self):
        before = PINE_BEFORE.read_text()
        after = PINE_AFTER.read_text()
        start = "// Original mode preserves the prior immediate-entry semantics exactly."
        end = "// Retest-gated official state changes only on a CLOSED candle"
        self.assertEqual(
            before[before.index(start) : before.index(end)],
            after[after.index(start) : after.index(end)],
        )


if __name__ == "__main__":
    unittest.main()
