"""Active-trade selection, panel rejection, and auto-right guards. No orders."""
from __future__ import annotations

import unittest
from decimal import Decimal

from cdx_vision.auto_right import run_navigation
from cdx_vision.config import VisionConfig
from cdx_vision.models import OCRToken
from cdx_vision.parser import is_noise, parse_tokens
from cdx_vision.service import VisionBridge
from cdx_vision.window_locator import WindowInfo


def _at(text: str, x: int, y: int) -> OCRToken:
    return OCRToken(text, x, y, x + 160, y + 16)


def _trade(prefix: str, x: int, sl: str, entry: str, tp1: str, tp2: str, side: str = "SHORT") -> list[OCRToken]:
    return [
        _at(f"CDX {side}", x, 20),
        _at(f"SL {sl}", x, 40),
        _at(f"CDX ENTRY {entry}", x, 90),
        _at(f"TP1 {tp1}", x, 140),
        _at(f"TP2 {tp2}", x, 190),
    ]


class _FakeNav:
    def __init__(self, *, focus: bool = True, foreground: bool = True, minimized: bool = False) -> None:
        self.focus = focus
        self.foreground = foreground
        self._minimized = minimized
        self.keypresses = 0

    def minimized(self, hwnd: int) -> bool:
        return self._minimized

    def focus_and_confirm(self, window: WindowInfo) -> bool:
        return self.focus

    def ctrl_right(self, window: WindowInfo) -> bool:
        if not self.foreground:
            return False
        self.keypresses += 1
        return True


def _window() -> WindowInfo:
    return WindowInfo(1, "NQ1!", 0, 0, 800, 600)


def _run(frames, side="SHORT", price="30909.50"):
    from datetime import datetime, timezone
    from pathlib import Path
    import tempfile

    from cdx_vision.ledger import VisionLedger
    from cdx_vision.models import VisionCaptureRequest

    root = Path(tempfile.mkdtemp())
    cfg = VisionConfig(enabled=True, root=root)
    bridge = VisionBridge(cfg, VisionLedger(cfg.ledger_path, root / "levels.csv"))
    now = datetime.now(timezone.utc)
    return bridge.process_frames(
        VisionCaptureRequest("h", side, "NQ", now, Decimal(price) if price else None),
        frames,
        now=now,
        window_title="TradingView",
    )


class SelectorTests(unittest.TestCase):
    def test_rightmost_current_short_beats_old_trade(self) -> None:
        tokens = _trade("old", 40, "29747.00", "29709.50", "29672.00", "29645.00")
        tokens += _trade("new", 800, "30947.00", "30909.50", "30872.00", "30845.00")
        tokens.append(_at("30818.25", 1100, 300))
        result = _run([tokens, tokens], price="30910.00")
        self.assertTrue(result.confirmed)
        self.assertEqual(result.entry_source, "VISION")
        self.assertEqual(result.visual_entry, Decimal("30909.50"))
        self.assertEqual(result.stop, Decimal("30947.00"))
        self.assertEqual(result.tp1, Decimal("30872.00"))
        self.assertEqual(result.tp2, Decimal("30845.00"))

    def test_old_trade_is_not_selected_when_price_points_at_it_but_it_is_left(self) -> None:
        tokens = _trade("old", 40, "29747.00", "29709.50", "29672.00", "29645.00")
        tokens.append(_at("30818.25", 1100, 300))
        result = _run([tokens, tokens], price="29709.50")
        self.assertFalse(result.confirmed)
        self.assertIn("VISION_REJECT_STALE_TRADE_LEVELS", result.reasons)
        self.assertIsNone(result.stop)

    def test_two_current_sets_are_ambiguous(self) -> None:
        tokens = _trade("a", 800, "30947.00", "30909.50", "30872.00", "30845.00")
        tokens += _trade("b", 860, "30940.00", "30920.00", "30900.00", "30880.00")
        tokens.append(_at("30818.25", 1100, 300))
        result = _run([tokens, tokens], price="30910.00")
        self.assertFalse(result.confirmed)
        self.assertIn("VISION_AMBIGUOUS_LEVEL_SET", result.reasons)

    def test_opposite_marker_on_the_current_trade_conflicts(self) -> None:
        tokens = _trade("long", 800, "30754.00", "30773.25", "30792.50", "30827.50", side="LONG")
        tokens.append(_at("30818.25", 1100, 300))
        result = _run([tokens, tokens], side="SHORT", price="30773.25")
        self.assertIn("VISION_DIRECTION_CONFLICT", result.reasons)


class PollutionTests(unittest.TestCase):
    def test_panels_and_scale_do_not_become_levels(self) -> None:
        noise = [
            _at("WIN RATE 79.4%", 900, 40),
            _at("RSI 47.88", 900, 70),
            _at("AVG RUNNER +6.53R", 900, 100),
            _at("TRADES 46", 900, 130),
            _at("07:12:01", 980, 160),
            _at("30890.00", 1000, 200),
            _at("VOLATILITY Low", 900, 10),
        ]
        for token in noise:
            self.assertTrue(is_noise(token.text) or parse_tokens([token])[0] == [])
        levels, _direction = parse_tokens(noise)
        self.assertEqual(levels, [])
        tokens = noise + _trade("now", 800, "30947.00", "30909.50", "30872.00", "30845.00")
        result = _run([tokens, tokens])
        self.assertEqual(result.stop, Decimal("30947.00"))
        self.assertEqual(result.tp1, Decimal("30872.00"))
        self.assertNotEqual(result.stop, Decimal("30890.00"))


class AutoRightTests(unittest.TestCase):
    def test_visible_chart_sends_no_keys(self) -> None:
        nav = _FakeNav()
        state = run_navigation(
            window=_window(),
            initial_tokens=[_at("SL 1", 1, 1)],
            initial_visible=True,
            read_once=lambda: ([], False),
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertFalse(state.triggered)
        self.assertEqual(nav.keypresses, 0)
        self.assertEqual(state.reason, "VISION_INITIAL_LEVELS_VISIBLE")

    def test_found_after_one_move_then_stops(self) -> None:
        nav = _FakeNav()
        script = [[True], [True]]

        def read_once():
            return [_at("SL 30947.00", 800, 40)], script.pop(0)[0]

        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=read_once,
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 1)
        self.assertEqual(state.attempts, 1)
        self.assertTrue(state.success)
        self.assertEqual(len(state.frames), 2)

    def test_found_after_two_moves(self) -> None:
        nav = _FakeNav()
        script = [False, True, True]

        def read_once():
            return [_at("x", 1, 1)], script.pop(0)

        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=read_once,
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 2)
        self.assertTrue(state.success)

    def test_exhausted_max_attempts(self) -> None:
        nav = _FakeNav()
        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=lambda: ([], False),
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 3)
        self.assertFalse(state.success)
        self.assertEqual(state.reason, "VISION_AUTO_RIGHT_EXHAUSTED")

    def test_focus_fail_sends_no_keys(self) -> None:
        nav = _FakeNav(focus=False)
        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=lambda: ([], True),
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 0)
        self.assertEqual(state.reason, "VISION_TRADINGVIEW_FOCUS_FAIL")

    def test_wrong_foreground_sends_no_keys(self) -> None:
        nav = _FakeNav(foreground=False)
        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=lambda: ([], True),
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 0)
        self.assertEqual(state.reason, "VISION_TRADINGVIEW_FOCUS_FAIL")

    def test_minimized_sends_no_keys(self) -> None:
        nav = _FakeNav(minimized=True)
        state = run_navigation(
            window=_window(),
            initial_tokens=[],
            initial_visible=False,
            read_once=lambda: ([], True),
            navigator=nav,
            max_attempts=3,
            redraw_s=0,
        )
        self.assertEqual(nav.keypresses, 0)
        self.assertEqual(state.reason, "VISION_TRADINGVIEW_MINIMIZED")

    def test_execution_stays_closed(self) -> None:
        cfg = VisionConfig(enabled=True, shadow_only=True, execution_enabled=True, auto_right_enabled=True)
        self.assertFalse(cfg.may_route_orders())
        bridge = VisionBridge(cfg)
        self.assertFalse(hasattr(bridge, "place_order"))


class KnownFixtureTests(unittest.TestCase):
    def test_golden_short_image(self) -> None:
        from pathlib import Path

        from PIL import Image

        from cdx_vision.entry_read import read_visual_entry
        from cdx_vision.ocr import TesseractOcr, chart_crop, preprocess
        from cdx_vision.tesseract_cmd import resolve_tesseract

        path = Path("cdx_vision/fixtures/real/cdx_real_01.png")
        exe = resolve_tesseract()
        if exe is None or not path.exists():
            self.skipTest("golden chart is not on this machine")
        image = Image.open(path)
        roi = (0.5, 0.12, 0.78, 0.82)
        engine = TesseractOcr(exe, psm=11)
        tokens = list(engine.recognize(preprocess(chart_crop(image, roi), scale=3)))
        observed = read_visual_entry(engine, image, roi, tokens, scale=3)
        tokens.extend(observed.tokens)
        result = _run([tokens, tokens], price="30910.25")
        self.assertEqual(observed.price, Decimal("30909.50"))
        self.assertEqual(result.entry_source, "VISION")
        self.assertEqual(result.visual_entry, Decimal("30909.50"))
        self.assertEqual(result.webhook_entry, Decimal("30910.25"))
        self.assertEqual(result.stop, Decimal("30947.00"))
        self.assertEqual(result.tp1, Decimal("30872.00"))
        self.assertEqual(result.tp2, Decimal("30845.00"))


if __name__ == "__main__":
    unittest.main()
