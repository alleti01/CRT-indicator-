"""The 78% crop clips CDX prices. The chart-pane crop keeps the decimals."""
from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from PIL import Image

from cdx_vision.level_roi import (
    detect_chart_pane_bounds,
    level_box,
    old_level_box,
    ocr_box,
    resolve_level_crop,
    roi_truncated,
)
from cdx_vision.ocr import TesseractOcr
from cdx_vision.parser import parse_price, parse_tokens
from cdx_vision.tesseract_cmd import resolve_tesseract

_FIXTURE = Path("cdx_vision/fixtures/real/roi_truncation_mnq.png")


class PriceTokenTests(unittest.TestCase):
    def test_cut_off_sl_is_not_a_price(self) -> None:
        self.assertIsNone(parse_price("SL_30785,"))
        self.assertEqual(parse_price("SL_30785.50"), Decimal("30785.50"))
        self.assertEqual(parse_price("30838"), Decimal("30838"))
        self.assertEqual(parse_price("30838.50"), Decimal("30838.50"))
        self.assertEqual(parse_price("30,838.50"), Decimal("30838.50"))


class RoiTests(unittest.TestCase):
    def setUp(self) -> None:
        if not _FIXTURE.exists():
            self.skipTest("fixture missing")
        self.image = Image.open(_FIXTURE)
        self.engine = TesseractOcr(resolve_tesseract(), psm=11)

    def tearDown(self) -> None:
        self.image.close()

    def test_old_roi_clips_the_prices(self) -> None:
        box = old_level_box(self.image)
        self.assertAlmostEqual(box[2] / self.image.size[0], 0.78, places=2)
        tokens = ocr_box(self.image, box, self.engine)
        self.assertTrue(roi_truncated(tokens, box))
        text = " ".join(token.text for token in tokens)
        self.assertIn("30838", text)
        self.assertNotIn("30838.50", text)

    def test_chart_pane_keeps_the_decimals(self) -> None:
        pane = detect_chart_pane_bounds(self.image)
        self.assertGreater(pane.right, int(self.image.size[0] * 0.80))
        self.assertLess(pane.right, int(self.image.size[0] * 0.99))
        state = resolve_level_crop(self.image, self.engine)
        self.assertFalse(state.truncated)
        levels, _direction = parse_tokens(state.tokens)
        found = {level.normalized_label: level.price for level in levels}
        self.assertEqual(found["ENTRY"], Decimal("30812.00"))
        self.assertEqual(found["SL"], Decimal("30785.50"))
        self.assertEqual(found["TP1"], Decimal("30838.50"))
        self.assertEqual(found["TP2"], Decimal("30871.75"))
        self.assertGreater(found["TP2"], found["TP1"])
        self.assertGreater(found["TP1"], found["ENTRY"])
        self.assertGreater(found["ENTRY"], found["SL"])
        from cdx_vision.consensus import consensus
        from cdx_vision.levels import frame_candidate

        frame, _reasons = frame_candidate(
            state.tokens,
            webhook_direction="LONG",
            webhook_price=Decimal("30825"),
            tick=Decimal("0.25"),
            sanity_points=Decimal("500"),
        )
        chosen, reasons, _unstable = consensus([frame, frame])
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.tp2, Decimal("30871.75"))
        self.assertIn("VISION_CONFIRMED", reasons)

    def test_bare_price_and_ribbon_are_not_tp2(self) -> None:
        from cdx_vision.models import OCRToken

        levels, _direction = parse_tokens([OCRToken("30871.75", 0, 0, 40, 12)])
        self.assertFalse(any(level.normalized_label == "TP2" for level in levels))
        for text in ("30922.55", "30912.08", "30901.61"):
            self.assertIsNone(parse_price(text))

    def test_expansion_recovers_a_clipped_crop(self) -> None:
        state = resolve_level_crop(self.image, self.engine, base=old_level_box(self.image))
        self.assertGreater(state.attempts, 0)
        self.assertFalse(state.unresolved)
        self.assertIn("VISION_ROI_EXPANSION_SUCCESS", state.reasons)
        levels, _direction = parse_tokens(state.tokens)
        found = {level.normalized_label: level.price for level in levels}
        self.assertEqual(found["TP1"], Decimal("30838.50"))
        self.assertEqual(found["SL"], Decimal("30785.50"))

    def test_resized_windows_keep_the_same_fraction(self) -> None:
        original = detect_chart_pane_bounds(self.image)
        fraction = original.right / self.image.size[0]
        for width in (1000, 1920):
            height = int(self.image.size[1] * width / self.image.size[0])
            resized = self.image.resize((width, height))
            pane = detect_chart_pane_bounds(resized)
            self.assertAlmostEqual(pane.right / width, fraction, delta=0.03)
            box = level_box(resized, pane)
            self.assertGreater(box[2], int(width * 0.78))


if __name__ == "__main__":
    unittest.main()
