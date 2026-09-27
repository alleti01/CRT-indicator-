"""Visual entry is preferred. Webhook and fill stay separate. No order path."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.ledger import VisionLedger, load_rows
from cdx_vision.models import VisionCaptureRequest, VisionState
from cdx_vision.parser import parse_price
from cdx_vision.service import VisionBridge
from cdx_vision.tests.test_vision import long_frame, short_frame


def _bridge() -> tuple[VisionBridge, Path]:
    root = Path(tempfile.mkdtemp())
    cfg = VisionConfig(enabled=True, root=root)
    bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, root / "levels.csv"))
    return bridge, root


def _run(bridge: VisionBridge, signal_id: str, side: str, frames, price, fill=None, now=None):
    now = now or datetime.now(timezone.utc)
    return bridge.process_frames(
        VisionCaptureRequest(signal_id, side, "NQ", now, price, fill),
        frames,
        now=now,
        window_title="TradingView",
    )


def _without_entry():
    return [token for token in short_frame() if "ENTRY" not in token.text]


class EntrySourceTests(unittest.TestCase):
    def test_clear_short_visual_entry_overrides_webhook(self) -> None:
        bridge, root = _bridge()
        result = _run(bridge, "short", "SHORT", [short_frame(), short_frame()], Decimal("30910.25"))
        self.assertEqual(result.state, VisionState.VISION_CONFIRMED)
        self.assertEqual(result.visual_entry, Decimal("30909.50"))
        self.assertEqual(result.webhook_entry, Decimal("30910.25"))
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertEqual(result.entry_source, "VISION")
        self.assertNotIn("VISION_ENTRY_WEBHOOK_MISMATCH", result.reasons)
        row = json.loads(root.joinpath("logs/vision_levels.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["schema_version"], "2")
        self.assertEqual(row["cdx_visual_entry"], "30909.50")
        self.assertEqual(row["webhook_entry"], "30910.25")
        self.assertEqual(row["cdx_native_entry"], "30909.50")
        self.assertEqual(row["entry_source"], "VISION")
        self.assertEqual(row["native_r_source"], "VISION")
        self.assertEqual(Decimal(row["native_r_points"]), Decimal("37.50"))
        self.assertEqual(Decimal(row["tp1_R"]), Decimal("1"))
        self.assertEqual(Decimal(row["tp2_R"]), Decimal("1.72"))
        self.assertEqual(Decimal(row["visual_vs_webhook_points"]), Decimal("0.75"))

    def test_clear_long_visual_entry(self) -> None:
        bridge, _root = _bridge()
        result = _run(bridge, "long", "LONG", [long_frame(), long_frame()], Decimal("30773.00"))
        self.assertEqual(result.entry_source, "VISION")
        self.assertEqual(result.visual_entry, Decimal("30773.25"))
        self.assertEqual(result.entry, Decimal("30773.25"))
        self.assertLess(result.stop, result.entry)
        self.assertLess(result.entry, result.tp1)
        self.assertLess(result.tp1, result.tp2)

    def test_visual_and_webhook_same(self) -> None:
        bridge, root = _bridge()
        result = _run(bridge, "same", "SHORT", [short_frame(), short_frame()], Decimal("30909.50"))
        self.assertEqual(result.entry_source, "VISION")
        row = json.loads((root / "logs" / "vision_levels.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(Decimal(row["visual_vs_webhook_points"]), Decimal("0"))

    def test_large_mismatch_is_recorded_and_visual_stays(self) -> None:
        bridge, _root = _bridge()
        result = _run(bridge, "far", "SHORT", [short_frame(), short_frame()], Decimal("31020.00"))
        self.assertEqual(result.state, VisionState.VISION_CONFIRMED)
        self.assertEqual(result.entry_source, "VISION")
        self.assertEqual(result.visual_entry, Decimal("30909.50"))
        self.assertEqual(result.webhook_entry, Decimal("31020.00"))
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertIn("VISION_ENTRY_WEBHOOK_MISMATCH", result.reasons)

    def test_missing_visual_uses_webhook_fallback(self) -> None:
        bridge, root = _bridge()
        frame = _without_entry()
        result = _run(bridge, "miss", "SHORT", [frame, frame], Decimal("30909.50"))
        self.assertEqual(result.state, VisionState.VISION_CONFIRMED)
        self.assertIsNone(result.visual_entry)
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertEqual(result.entry_source, "WEBHOOK")
        self.assertIn("VISION_ENTRY_NOT_FOUND_WEBHOOK_FALLBACK", result.reasons)
        row = json.loads((root / "logs" / "vision_levels.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["cdx_visual_entry"], "")
        self.assertEqual(row["native_r_source"], "WEBHOOK_FALLBACK")
        self.assertEqual(Decimal(row["tp1_R"]), Decimal("1"))

    def test_missing_both_entry_sources(self) -> None:
        bridge, _root = _bridge()
        frame = _without_entry()
        result = _run(bridge, "none", "SHORT", [frame, frame], None)
        self.assertFalse(result.confirmed)
        self.assertEqual(result.entry_source, "MISSING")
        self.assertIn("VISION_REJECT_ENTRY_UNAVAILABLE", result.reasons)

    def test_off_tick_visual_entry_is_not_invented(self) -> None:
        self.assertIsNone(parse_price("30909.53"))
        self.assertNotEqual(parse_price("3090950"), Decimal("30909.50"))
        bridge, _root = _bridge()
        frame = _without_entry() + [short_frame()[0].__class__("CDX ENTRY 30909.53", 120, 120, 300, 136)]
        result = _run(bridge, "tick", "SHORT", [frame, frame], Decimal("30909.50"))
        self.assertIsNone(result.visual_entry)
        self.assertEqual(result.entry_source, "WEBHOOK")
        self.assertEqual(result.entry, Decimal("30909.50"))

    def test_huge_undecimaled_price_does_not_become_the_entry(self) -> None:
        bridge, _root = _bridge()
        token = short_frame()[0].__class__("CDX ENTRY 309095", 120, 120, 300, 136)
        frame = _without_entry() + [token]
        result = _run(bridge, "huge", "SHORT", [frame, frame], Decimal("30909.50"))
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertEqual(result.entry_source, "WEBHOOK")
        self.assertNotEqual(result.visual_entry, Decimal("30909.50"))

    def test_unstable_two_frame_entry_falls_back(self) -> None:
        bridge, _root = _bridge()
        frames = [short_frame(entry="30909.50"), short_frame(entry="30909.75")]
        result = _run(bridge, "unstable", "SHORT", frames, Decimal("30909.50"))
        self.assertEqual(result.state, VisionState.VISION_CONFIRMED)
        self.assertEqual(result.entry_source, "WEBHOOK")
        self.assertIsNone(result.visual_entry)
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertIn("VISION_ENTRY_UNSTABLE", result.reasons)

    def test_fill_is_logged_separately(self) -> None:
        bridge, root = _bridge()
        result = _run(
            bridge,
            "fill",
            "SHORT",
            [short_frame(), short_frame()],
            Decimal("30909.50"),
            Decimal("30908.25"),
        )
        self.assertEqual(result.entry_source, "VISION")
        self.assertEqual(result.actual_fill, Decimal("30908.25"))
        row = json.loads((root / "logs" / "vision_levels.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["actual_fill"], "30908.25")
        self.assertEqual(Decimal(row["fill_vs_visual_points"]), Decimal("-1.25"))
        self.assertEqual(Decimal(row["absolute_fill_vs_visual_points"]), Decimal("1.25"))
        self.assertEqual(Decimal(row["fill_vs_webhook_points"]), Decimal("-1.25"))

    def test_fill_fallback_when_nothing_else_exists(self) -> None:
        bridge, root = _bridge()
        frame = _without_entry()
        result = _run(bridge, "fillonly", "SHORT", [frame, frame], None, Decimal("30909.50"))
        self.assertEqual(result.entry_source, "FILL")
        self.assertEqual(result.entry, Decimal("30909.50"))
        self.assertIsNone(result.visual_entry)
        row = json.loads((root / "logs" / "vision_levels.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(row["native_r_source"], "FILL_FALLBACK")

    def test_old_ledger_row_still_loads(self) -> None:
        root = Path(tempfile.mkdtemp())
        path = root / "vision_levels.jsonl"
        path.write_text(json.dumps({"schema_version": "1.0", "signal_id": "old", "entry": "1"}) + "\n", encoding="utf-8")
        rows = load_rows(path)
        self.assertEqual(rows[0]["cdx_visual_entry"], "")
        self.assertEqual(rows[0]["cdx_native_entry"], "1")

    def test_csv_header_grows_without_rewriting_old_row(self) -> None:
        root = Path(tempfile.mkdtemp())
        csv_path = root / "levels.csv"
        csv_path.write_text(
            "signal_id,timestamp,direction,fill_price,cdx_entry,cdx_stop,cdx_tp1,cdx_tp2,"
            "cdx_stop_points,bot_stop,bot_stop_points,cdx_stop_hit,bot_stop_hit,"
            "reached_cdx_tp1,reached_cdx_tp2,vision_status\n"
            "OLD,t,SHORT,,1,2,3,4,1,,,,,,,VISION_CONFIRMED\n",
            encoding="utf-8",
        )
        bridge = VisionBridge(VisionConfig(enabled=True, root=root), VisionLedger(root / "v.jsonl", csv_path))
        _run(bridge, "new", "SHORT", [short_frame(), short_frame()], Decimal("30909.50"))
        text = csv_path.read_text(encoding="utf-8")
        self.assertIn("cdx_visual_entry", text.splitlines()[0])
        self.assertIn("OLD,t,SHORT,,1,2,3,4,1,,,,,,,VISION_CONFIRMED", text)
        self.assertIn("30909.50", text)

    def test_execution_stays_closed(self) -> None:
        cfg = VisionConfig(enabled=True, shadow_only=True, execution_enabled=True)
        self.assertFalse(cfg.may_route_orders())
        bridge, _root = _bridge()
        self.assertFalse(bridge.may_route_orders())
        self.assertFalse(hasattr(bridge, "place_order"))


class KnownScreenshotTests(unittest.TestCase):
    def test_saved_chart_reads_visual_entry(self) -> None:
        from cdx_vision.entry_read import read_visual_entry
        from cdx_vision.ocr import TesseractOcr
        from cdx_vision.tesseract_cmd import resolve_tesseract

        image_path = Path("cdx_vision/debug/manual_20260927_175439/window.png")
        exe = resolve_tesseract()
        if exe is None or not image_path.exists():
            self.skipTest("saved chart or tesseract is not on this machine")
        from PIL import Image

        observed = read_visual_entry(
            TesseractOcr(exe),
            Image.open(image_path),
            (0.5, 0.12, 0.78, 0.82),
            [],
        )
        self.assertEqual(observed.status, "AGREED")
        self.assertEqual(observed.price, Decimal("30909.50"))


if __name__ == "__main__":
    unittest.main()
