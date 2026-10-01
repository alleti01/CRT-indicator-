"""Chart-state rules. A CDX marker is not a finished level set. No orders."""
from __future__ import annotations

import unittest
from decimal import Decimal

from cdx_vision.chart_state import (
    detect_symbol,
    detect_timeframe,
    interval_keystrokes,
    interval_menu_target,
    menu_row_matches,
    label_flags,
    normalize_timeframe,
    recovery_route,
    ribbon_values,
    signal_marker_visible,
    symbol_matches,
)
from cdx_vision.models import OCRToken
from cdx_vision.parser import parse_price
from cdx_vision.window_locator import WindowInfo, select_bot_window


def _at(text: str, x: int, y: int) -> OCRToken:
    return OCRToken(text, x, y, x + 40, y + 12)


class TimeframeTests(unittest.TestCase):
    def test_toolbar_3m_ignores_30s_in_the_alerts_panel(self) -> None:
        words = [("3m", 80, 40), ("30s", 900, 40), ("1m", 900, 80)]
        self.assertEqual(detect_timeframe(words, width=1000, height=800), "3m")

    def test_three_minutes_is_not_typed_as_three_months(self) -> None:
        self.assertEqual(interval_keystrokes("3m"), "3")
        self.assertNotIn("M", interval_keystrokes("3m"))
        self.assertEqual(interval_keystrokes("1m"), "1")
        self.assertEqual(interval_keystrokes("30s"), "30S")
        self.assertEqual(interval_menu_target("3m"), ("3", "minute"))
        self.assertTrue(menu_row_matches("3 minutes", "3", "minute"))
        self.assertTrue(menu_row_matches("j3minutes", "3", "minute"))
        self.assertFalse(menu_row_matches("15 minutes", "5", "minute"))
        self.assertFalse(menu_row_matches("15 minutes", "1", "minute"))
        self.assertFalse(menu_row_matches("3 hours", "3", "minute"))
        self.assertTrue(menu_row_matches("1 minute", "1", "minute"))

    def test_symbol_is_the_bot_root(self) -> None:
        self.assertEqual(detect_symbol("MNQ1! 30,969"), "MNQ")
        self.assertEqual(detect_symbol("NQ1!"), "NQ")
        self.assertTrue(symbol_matches("MNQ1! bot", "MNQ"))
        self.assertFalse(symbol_matches("ES1! manual", "MNQ"))
        self.assertFalse(symbol_matches("NQ1!", "MNQ"))

    def test_one_minute_and_thirty_seconds(self) -> None:
        self.assertEqual(detect_timeframe([("1m", 70, 30)], width=1000, height=800), "1m")
        self.assertEqual(detect_timeframe([("30s", 70, 30)], width=1000, height=800), "30s")
        self.assertEqual(detect_timeframe([("15s", 70, 30)], width=1000, height=800), "15s")
        self.assertEqual(normalize_timeframe("3 minutes"), "3m")

    def test_wrong_timeframe_is_restored_before_any_pan(self) -> None:
        self.assertEqual(
            recovery_route(timeframe_ok=False, level_set_complete=False, live_edge=False, offscreen=True),
            "RESTORE_TIMEFRAME",
        )


class MarkerTests(unittest.TestCase):
    def test_marker_without_levels_is_not_complete(self) -> None:
        tokens = [_at("CDX LONG", 400, 80)]
        self.assertTrue(signal_marker_visible(tokens))
        flags = label_flags(tokens)
        self.assertFalse(flags["entry"] or flags["sl"] or flags["tp1"] or flags["tp2"])
        route = recovery_route(timeframe_ok=True, level_set_complete=False, live_edge=False, offscreen=True)
        self.assertEqual(route, "AUTO_RIGHT")

    def test_complete_labels_do_not_pan(self) -> None:
        self.assertEqual(
            recovery_route(timeframe_ok=True, level_set_complete=True, live_edge=False, offscreen=True),
            "READY",
        )

    def test_live_edge_does_not_keep_panning(self) -> None:
        self.assertEqual(
            recovery_route(timeframe_ok=True, level_set_complete=False, live_edge=True, offscreen=False),
            "NATIVE_LABELS_MISSING",
        )


class RibbonTests(unittest.TestCase):
    def test_ribbon_prices_never_become_levels(self) -> None:
        tokens = [_at(text, 700, 40 + i * 20) for i, text in enumerate(("30922.55", "30912.08", "30901.61"))]
        rejected = ribbon_values(tokens)
        self.assertEqual(len(rejected), 3)
        for text in ("30922.55", "30912.08", "30901.61"):
            self.assertIsNone(parse_price(text))
        self.assertEqual(parse_price("30909.50"), Decimal("30909.50"))


class WindowTests(unittest.TestCase):
    def test_bot_chart_is_not_the_manual_chart(self) -> None:
        manual = WindowInfo(1, "MNQ1! 30s manual", 0, 0, 800, 600)
        bot = WindowInfo(2, "MNQ1! 3m bot", 0, 0, 1400, 900)
        other = WindowInfo(3, "ES1!", 0, 0, 1400, 900)
        chosen = select_bot_window([manual, other, bot], "3m bot")
        self.assertEqual(chosen.hwnd, 2)
        self.assertIsNone(select_bot_window([other], "MNQ"))


if __name__ == "__main__":
    unittest.main()
