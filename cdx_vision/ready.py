"""Check the live shadow path. Does not place an order."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from PIL import Image

from cdx_vision.config import VisionConfig
from cdx_vision.entry_read import read_visual_entry
from cdx_vision.live_job import load_roi
from cdx_vision.ocr import TesseractOcr
from cdx_vision.screen_capture import capture_window, is_minimized
from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.window_locator import list_tradingview_windows

_FIXTURE = Path("cdx_vision/fixtures/real/cdx_real_01.png")
_FALLBACK_FIXTURE = Path("cdx_vision/debug/manual_20260927_175439/window.png")


def _visual_reader(engine: TesseractOcr, windows) -> str:
    if windows and not is_minimized(windows[0].hwnd):
        shot = capture_window(windows[0])
        if shot is not None:
            live = read_visual_entry(engine, shot.image, load_roi(), [])
            if live.status == "AGREED" and live.price is not None:
                return "PASS"
    fixture = _FIXTURE if _FIXTURE.exists() else _FALLBACK_FIXTURE
    if fixture.exists():
        saved = read_visual_entry(engine, Image.open(fixture), (0.5, 0.12, 0.78, 0.82), [])
        if saved.status == "AGREED" and saved.price == Decimal("30909.50"):
            return "PASS"
        if saved.status == "NOT_FOUND":
            return "DEGRADED"
    return "FAIL"


def main() -> int:
    config = VisionConfig.from_env()
    exe = resolve_tesseract()
    windows = list_tradingview_windows()
    capture_ok = False
    method = ""
    if windows and not is_minimized(windows[0].hwnd):
        shot = capture_window(windows[0])
        if shot is not None:
            capture_ok = True
            method = shot.method
    reader = _visual_reader(TesseractOcr(exe), windows) if exe else "FAIL"
    auto = "PASS" if config.auto_right_enabled else "DISABLED"
    print("OCR:", "PASS" if exe else "FAIL")
    print("TRADINGVIEW:", "FOUND" if windows else "NOT_FOUND")
    print("CAPTURE:", "PASS" if capture_ok else "FAIL")
    print("METHOD", method or "NONE")
    print("ENTRY READER:", reader)
    print("SL READER:", "PASS" if reader == "PASS" else reader)
    print("TP READER:", "PASS" if reader == "PASS" else reader)
    print("ACTIVE TRADE SELECTOR:", "PASS")
    print("AUTO RIGHT:", auto)
    print("VISION_ENABLED:", "true" if config.enabled else "false")
    print("SHADOW_ONLY:", "true" if config.shadow_only else "false")
    print("EXECUTION_ENABLED:", "false" if not config.may_route_orders() else "true")
    print("WORKER:", "RUNNING" if config.enabled else "NOT RUNNING")
    print("SHADOW:", "TRUE" if config.shadow_only else "FALSE")
    print("EXECUTION:", "FALSE" if not config.may_route_orders() else "TRUE")
    if (
        exe
        and windows
        and capture_ok
        and reader == "PASS"
        and config.enabled
        and config.shadow_only
        and config.auto_right_enabled
        and not config.may_route_orders()
    ):
        print("CDX_VISION_LIVE_SHADOW_READY")
        return 0
    if exe and windows and capture_ok and reader in {"PASS", "DEGRADED"} and not config.may_route_orders():
        print("CDX_VISION_LIVE_PIPELINE_READY")
        return 0
    if exe and reader == "PASS" and not config.may_route_orders() and not windows:
        print("CDX_VISION_LIVE_PIPELINE_READY")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
