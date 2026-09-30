"""Visible-tag extraction and live-edge routing. No orders."""
from __future__ import annotations

import unittest
from decimal import Decimal

from PIL import Image, ImageDraw, ImageFont

from cdx_vision.models import OCRToken, Reason
from cdx_vision.symbols import accepted_chart_symbol, market_root
from cdx_vision.validator import ordered
from cdx_vision.visible_levels import LineHit, TagHit, assemble, vertical_clip
from cdx_vision.visible_route import current_signal_visible, extraction_route


def _font(size: int):
    try:
        return ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _tag(price: str, y: int, color: str, linked: bool) -> TagHit:
    return TagHit(price, Decimal(price), 600, y, 700, y + 16, color, y + 8 if linked else None, "" if linked else "NO_CDX_LINE")


class SymbolTests(unittest.TestCase):
    def test_mnq_and_nq_are_accepted(self) -> None:
        self.assertEqual(market_root("MNQ1!"), "MNQ")
        self.assertEqual(market_root("MNQ 12-26"), "MNQ")
        self.assertEqual(market_root("NQ1!"), "NQ")
        self.assertTrue(accepted_chart_symbol("MNQ1!"))
        self.assertTrue(accepted_chart_symbol("MNQ 12-26"))
        self.assertTrue(accepted_chart_symbol("NQ1!"))
        self.assertFalse(accepted_chart_symbol("ES1!"))


class RouteTests(unittest.TestCase):
    def test_offscreen_may_pan(self) -> None:
        self.assertEqual(extraction_route(levels_visible=False, marker_visible=False), "AUTO_RIGHT")

    def test_visible_marker_does_not_pan(self) -> None:
        tokens = [OCRToken("CDX", 500, 10, 540, 24), OCRToken("LONG", 550, 10, 610, 24)]
        self.assertTrue(current_signal_visible(tokens))
        self.assertEqual(extraction_route(levels_visible=False, marker_visible=True), "VISIBLE_EXTRACTION")

    def test_ready_levels_skip_both(self) -> None:
        self.assertEqual(extraction_route(levels_visible=True, marker_visible=True), "READY")


class AssembleTests(unittest.TestCase):
    def test_long_geometry_from_associated_tags(self) -> None:
        tags = [
            _tag("30658.25", 200, "red", True),
            _tag("30780.00", 80, "green", True),
            _tag("30820.00", 40, "green", True),
            _tag("30773.50", 10, "green", False),
        ]
        read = assemble(tags, direction="LONG", webhook_price=Decimal("30730.25"))
        self.assertEqual(read.stop, Decimal("30658.25"))
        self.assertEqual(read.tp1, Decimal("30780.00"))
        self.assertEqual(read.tp2, Decimal("30820.00"))
        self.assertEqual(read.entry_source, "WEBHOOK")
        self.assertFalse(read.reasons)
        self.assertTrue(ordered("LONG", read.entry, read.stop, read.tp1, read.tp2))

    def test_unlinked_green_tag_is_not_a_level(self) -> None:
        tags = [_tag("30658.25", 80, "green", False)]
        read = assemble(tags, direction="LONG", webhook_price=Decimal("30730.25"))
        self.assertIsNone(read.tp1)
        self.assertIn(Reason.VISION_TP1_NOT_FOUND.value, read.reasons)

    def test_label_and_tag_conflict_rejects(self) -> None:
        from cdx_vision.models import ParsedLevel

        label = ParsedLevel("SL 30640.25", "SL", Decimal("30640.25"), 1, 1, 2, 2)
        tags = [
            _tag("30658.25", 200, "red", True),
            _tag("30780.00", 80, "green", True),
            _tag("30820.00", 40, "green", True),
        ]
        read = assemble(tags, direction="LONG", webhook_price=Decimal("30730.25"), label_levels=[label])
        self.assertIn(Reason.VISION_LEVEL_CONFLICT.value, read.reasons)
        self.assertIsNone(read.stop)

    def test_short_ordering(self) -> None:
        self.assertTrue(ordered("SHORT", Decimal("30909.50"), Decimal("30947.00"), Decimal("30872.00"), Decimal("30845.00")))
        self.assertFalse(ordered("LONG", Decimal("30730.25"), Decimal("30740.00"), Decimal("30780.00"), Decimal("30820.00")))

    def test_edge_line_is_vertical_clip(self) -> None:
        self.assertTrue(vertical_clip([LineHit(120, 0, 10, "green")], 1000, (0.0, 0.12, 1.0, 0.9)))
        self.assertFalse(vertical_clip([LineHit(400, 0, 10, "green")], 1000, (0.0, 0.12, 1.0, 0.9)))

    def test_off_tick_text_is_not_a_price(self) -> None:
        from cdx_vision.parser import parse_price

        self.assertIsNone(parse_price("30575.80"))
        self.assertEqual(parse_price("30658.25"), Decimal("30658.25"))


class DrawnTagTests(unittest.TestCase):
    def test_line_linked_tag_is_read_and_bare_tag_is_not(self) -> None:
        from cdx_vision.tesseract_cmd import resolve_tesseract
        from cdx_vision.visible_levels import read_visible_tags

        exe = resolve_tesseract()
        if exe is None:
            self.skipTest("tesseract is not installed")
        image = Image.new("RGB", (1000, 600), (8, 12, 20))
        draw = ImageDraw.Draw(image)
        draw.line((120, 240, 700, 240), fill=(220, 40, 50), width=3)
        draw.rectangle((620, 228, 760, 254), fill=(220, 40, 50))
        draw.text((630, 230), "30572.50", fill=(0, 0, 0), font=_font(18))
        draw.rectangle((620, 320, 760, 346), fill=(40, 220, 60))
        draw.text((630, 322), "30773.50", fill=(0, 0, 0), font=_font(18))

        class Engine:
            executable = exe

            def recognize(self, item):
                return []

        tags, lines = read_visible_tags(image, Engine())
        linked = [tag for tag in tags if tag.price == Decimal("30572.50") and tag.associated]
        bare = [tag for tag in tags if tag.price == Decimal("30773.50")]
        self.assertTrue(lines)
        self.assertTrue(linked)
        self.assertTrue(bare)
        self.assertEqual(bare[0].reject, "NO_CDX_LINE")


if __name__ == "__main__":
    unittest.main()
