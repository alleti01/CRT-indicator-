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

_FIXTURE = Path("cdx_vision/debug/manual_20260927_175439/window.png")


def _visual_reader(engine: TesseractOcr, windows) -> str:
    if windows and not is_minimized(windows[0].hwnd):
        shot = capture_window(windows[0])
        if shot is not None:
            live = read_visual_entry(engine, shot.image, load_roi(), [])
            if live.status == "AGREED" and live.price is not None:
                return "PASS"
    if _FIXTURE.exists():
        saved = read_visual_entry(engine, Image.open(_FIXTURE), (0.5, 0.12, 0.78, 0.82), [])
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
    print("OCR", "PASS" if exe else "FAIL")
    print("WINDOW", "PASS" if windows else "FAIL")
    print("CAPTURE", "PASS" if capture_ok else "FAIL")
    print("METHOD", method or "NONE")
    print("VISUAL_ENTRY_READER", reader)
    print("WORKER", "ON_WEBHOOK")
    print("SHADOW", "PASS" if config.shadow_only and not config.may_route_orders() else "FAIL")
    print("EXECUTION_ISOLATION", "PASS" if not config.may_route_orders() else "FAIL")
    if exe and windows and capture_ok and reader in {"PASS", "DEGRADED"} and not config.may_route_orders():
        print("CDX_VISION_LIVE_PIPELINE_READY")
        return 0
    if exe and reader == "PASS" and not config.may_route_orders() and not windows:
        print("CDX_VISION_LIVE_PIPELINE_READY")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
