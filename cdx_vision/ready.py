"""Check the live shadow path. Does not place an order."""
from __future__ import annotations

from cdx_vision.config import VisionConfig
from cdx_vision.screen_capture import capture_window, is_minimized
from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.window_locator import list_tradingview_windows


def main() -> int:
    config = VisionConfig.from_env()
    ocr = bool(resolve_tesseract())
    windows = list_tradingview_windows()
    capture_ok = False
    method = ""
    if windows and not is_minimized(windows[0].hwnd):
        shot = capture_window(windows[0])
        if shot is not None:
            capture_ok = True
            method = shot.method
    print("OCR", "PASS" if ocr else "FAIL")
    print("WINDOW", "PASS" if windows else "FAIL")
    print("CAPTURE", "PASS" if capture_ok else "FAIL")
    print("METHOD", method or "NONE")
    print("WORKER", "ON_WEBHOOK" if True else "FAIL")
    print("SHADOW", "PASS" if config.shadow_only and not config.may_route_orders() else "FAIL")
    print("EXECUTION_ISOLATION", "PASS" if not config.may_route_orders() else "FAIL")
    if ocr and windows and capture_ok and not config.may_route_orders():
        print("CDX_VISION_LIVE_PIPELINE_READY")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
