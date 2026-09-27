"""Parser, geometry, consensus, and the rule that vision cannot place an order."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.consensus import consensus
from cdx_vision.ledger import VisionLedger
from cdx_vision.models import CDXLevelCandidate, OCRToken, VisionCaptureRequest, VisionState
from cdx_vision.parser import normalize_label, on_tick, parse_price, parse_tokens
from cdx_vision.service import VisionBridge


def _token(text: str, y: int, x: int = 400) -> OCRToken:
    return OCRToken(text, x, y, x + 180, y + 16)


def short_frame(sl="30947.00", tp1="30872.00", tp2="30845.00", entry="30909.50") -> list[OCRToken]:
    return [
        _token(f"CDX SHORT {entry}", 80),
        _token(f"SL {sl}", 40),
        _token(f"CDX ENTRY {entry}", 120),
        _token(f"TP1 {tp1}", 200),
        _token(f"TP2 {tp2}", 260),
    ]


def long_frame() -> list[OCRToken]:
    return [
        _token("CDX LONG 30773.25", 200),
        _token("SL 30754.00", 260),
        _token("CDX ENTRY 30773.25", 180),
        _token("TP1 30792.50", 100),
        _token("TP2 30827.50", 40),
    ]


class ParserTests(unittest.TestCase):
    def test_tick_and_labels(self) -> None:
        self.assertTrue(on_tick(Decimal("30947.00")))
        self.assertFalse(on_tick(Decimal("30947.10")))
        self.assertEqual(parse_price("SL   30947.00"), Decimal("30947.00"))
        self.assertIsNone(parse_price("SL 30947.10"))
        self.assertEqual(normalize_label("tp 1 30872.00"), "TP1")
        self.assertEqual(normalize_label("TPI 30872.00"), "TP1")

    def test_known_short_relationships(self) -> None:
        levels, direction = parse_tokens(short_frame())
        prices = {level.normalized_label: level.price for level in levels}
        self.assertEqual(direction, "SHORT")
        self.assertEqual(prices["ENTRY"], Decimal("30909.50"))
        self.assertEqual(prices["SL"], Decimal("30947.00"))
        self.assertEqual(prices["TP1"], Decimal("30872.00"))
        self.assertEqual(prices["TP2"], Decimal("30845.00"))
        self.assertGreater(prices["SL"], prices["ENTRY"])
        self.assertGreater(prices["ENTRY"], prices["TP1"])
        self.assertGreater(prices["TP1"], prices["TP2"])
        stop = prices["SL"] - prices["ENTRY"]
        tp1 = prices["ENTRY"] - prices["TP1"]
        tp2 = prices["ENTRY"] - prices["TP2"]
        self.assertEqual(stop, Decimal("37.50"))
        self.assertEqual(tp1, Decimal("37.50"))
        self.assertEqual(tp2, Decimal("64.50"))


class GeometryTests(unittest.TestCase):
    def test_long_and_short_and_conflict(self) -> None:
        now = datetime.now(timezone.utc)
        cfg = VisionConfig(enabled=True, root=Path(tempfile.mkdtemp()))
        ledger = VisionLedger(cfg.ledger_path, cfg.root / "levels.csv")
        bridge = VisionBridge(cfg, ledger)
        short = bridge.process_frames(
            VisionCaptureRequest("s", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(), short_frame()],
            now=now,
            window_title="TradingView",
        )
        self.assertEqual(short.state, VisionState.VISION_CONFIRMED)
        long = bridge.process_frames(
            VisionCaptureRequest("l", "LONG", "NQ", now, Decimal("30773.25")),
            [long_frame(), long_frame()],
            now=now,
            window_title="TradingView",
        )
        self.assertEqual(long.state, VisionState.VISION_CONFIRMED)
        conflict = bridge.process_frames(
            VisionCaptureRequest("c", "SHORT", "NQ", now, Decimal("30909.50")),
            [long_frame(), long_frame()],
            now=now,
            window_title="TradingView",
        )
        self.assertIn("VISION_DIRECTION_CONFLICT", conflict.reasons)

    def test_missing_off_tick_and_bad_order(self) -> None:
        now = datetime.now(timezone.utc)
        cfg = VisionConfig(enabled=True, root=Path(tempfile.mkdtemp()))
        bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, cfg.root / "levels.csv"))
        missing = bridge.process_frames(
            VisionCaptureRequest("m", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(tp2=""), short_frame(tp2="")],
            now=now,
            window_title="TradingView",
        )
        self.assertFalse(missing.confirmed)
        bad = bridge.process_frames(
            VisionCaptureRequest("b", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(sl="30800.00"), short_frame(sl="30800.00")],
            now=now,
            window_title="TradingView",
        )
        self.assertIn("VISION_INVALID_ORDERING", bad.reasons)


class ConsensusTests(unittest.TestCase):
    def test_consecutive_match_and_unstable_majority(self) -> None:
        now = datetime.now(timezone.utc)
        cfg = VisionConfig(enabled=True, root=Path(tempfile.mkdtemp()))
        bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, cfg.root / "levels.csv"))
        ok = bridge.process_frames(
            VisionCaptureRequest("ok", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(), short_frame()],
            now=now,
            window_title="TradingView",
        )
        self.assertTrue(ok.confirmed)
        self.assertEqual(ok.stop, Decimal("30947.00"))
        unstable = bridge.process_frames(
            VisionCaptureRequest("bad", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(sl="30947.00"), short_frame(sl="30974.00"), short_frame(sl="30947.00")],
            now=now,
            window_title="TradingView",
        )
        self.assertFalse(unstable.confirmed)
        self.assertTrue(unstable.ocr_unstable)
        self.assertIn("VISION_NO_CONSENSUS", unstable.reasons)

    def test_duplicate_timeout_and_restart(self) -> None:
        now = datetime.now(timezone.utc)
        cfg = VisionConfig(enabled=True, root=Path(tempfile.mkdtemp()))
        bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, cfg.root / "levels.csv"))
        bridge.started_at = now - timedelta(minutes=2)
        request = VisionCaptureRequest("dup", "SHORT", "NQ", now, Decimal("30909.50"))
        first = bridge.process_frames(request, [short_frame(), short_frame()], now=now, window_title="TV")
        second = bridge.process_frames(request, [short_frame(sl="30974.00"), short_frame(sl="30974.00")], now=now, window_title="TV")
        self.assertEqual(first.stop, second.stop)
        self.assertIn("VISION_DUPLICATE", second.reasons)
        stale = VisionCaptureRequest("old", "SHORT", "NQ", now - timedelta(hours=1), Decimal("30909.50"))
        rejected = bridge.process_frames(stale, [short_frame(), short_frame()], now=now, window_title="TV")
        self.assertIn("VISION_REJECT_RESTART_STALE", rejected.reasons)
        late = VisionCaptureRequest("late", "SHORT", "NQ", now - timedelta(seconds=30), Decimal("30909.50"))
        timed = bridge.process_frames(late, [short_frame(), short_frame()], now=now, window_title="TV")
        self.assertEqual(timed.state, VisionState.VISION_TIMEOUT)


class IsolationTests(unittest.TestCase):
    def test_funded_flag_still_cannot_route(self) -> None:
        cfg = VisionConfig(enabled=True, shadow_only=True, execution_enabled=True)
        bridge = VisionBridge(cfg, VisionLedger(Path(tempfile.mkdtemp()) / "v.jsonl", Path(tempfile.mkdtemp()) / "c.csv"))
        self.assertFalse(cfg.may_route_orders())
        self.assertFalse(bridge.may_route_orders())
        self.assertFalse(hasattr(bridge, "place_order"))

    def test_disabled_hook_does_not_start_work(self) -> None:
        from cdx_vision.shadow_hook import enqueue_shadow

        class _Signal:
            signal_id = "x"
            direction = "SHORT"
            symbol = "NQ"
            signal_price = 30909.5

        enqueue_shadow(_Signal(), datetime.now(timezone.utc))

    def test_ledger_appends(self) -> None:
        root = Path(tempfile.mkdtemp())
        cfg = VisionConfig(enabled=True, root=root)
        bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, root / "levels.csv"))
        now = datetime.now(timezone.utc)
        bridge.process_frames(
            VisionCaptureRequest("row", "SHORT", "NQ", now, Decimal("30909.50")),
            [short_frame(), short_frame()],
            now=now,
            window_title="TradingView",
        )
        text = cfg.ledger_path.read_text(encoding="utf-8")
        self.assertIn("30947.00", text)
        self.assertEqual(text.count("\n"), 1)


class ConsensusUnitTests(unittest.TestCase):
    def test_direct_consensus_rejects_split(self) -> None:
        a = CDXLevelCandidate("SHORT", Decimal("30909.50"), "VISION", Decimal("30947.00"), Decimal("30872.00"), Decimal("30845.00"), ())
        b = CDXLevelCandidate("SHORT", Decimal("30909.50"), "VISION", Decimal("30974.00"), Decimal("30872.00"), Decimal("30845.00"), ())
        chosen, reasons, unstable = consensus([a, b, a])
        self.assertIsNone(chosen)
        self.assertTrue(unstable)
        self.assertIn("VISION_NO_CONSENSUS", reasons)


if __name__ == "__main__":
    unittest.main()
