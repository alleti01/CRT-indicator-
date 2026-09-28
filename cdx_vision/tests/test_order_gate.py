"""An order is allowed only when the chart read has all four prices."""
from __future__ import annotations

import unittest
from decimal import Decimal

from cdx_vision.models import VisionResult, VisionState
from cdx_vision.order_gate import levels_allow_order


def _result(**kwargs) -> VisionResult:
    base = dict(
        signal_id="sig",
        state=VisionState.VISION_CONFIRMED,
        direction="SHORT",
        native_entry=Decimal("30650.00"),
        stop=Decimal("30664.25"),
        tp1=Decimal("30635.75"),
        tp2=Decimal("30621.50"),
        initial_levels_visible=True,
    )
    base.update(kwargs)
    return VisionResult(**base)


class OrderGateTests(unittest.TestCase):
    def test_complete_short_allows_order(self) -> None:
        ok, why = levels_allow_order(_result())
        self.assertTrue(ok)
        self.assertEqual(why, "LEVELS_PULLED")

    def test_rejected_read_blocks_order(self) -> None:
        ok, why = levels_allow_order(_result(state=VisionState.VISION_REJECTED, reasons=["VISION_NO_CONSENSUS"]))
        self.assertFalse(ok)
        self.assertEqual(why, "VISION_NOT_CONFIRMED")

    def test_missing_target_blocks_order(self) -> None:
        ok, why = levels_allow_order(_result(tp2=None))
        self.assertFalse(ok)
        self.assertEqual(why, "MISSING_LEVEL")

    def test_levels_off_screen_block_order(self) -> None:
        ok, why = levels_allow_order(_result(initial_levels_visible=False, auto_right_success=False))
        self.assertFalse(ok)
        self.assertEqual(why, "LEVELS_NOT_ON_SCREEN")
