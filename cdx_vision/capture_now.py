"""Capture the TradingView app once. Does not read labels or place orders."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from cdx_vision.screen_capture import capture_window, is_minimized
from cdx_vision.window_locator import list_tradingview_windows


def main() -> int:
    windows = list_tradingview_windows()
    if not windows:
        print("VISION_WINDOW_NOT_FOUND")
        return 2
    window = windows[0]
    print("WINDOW_FOUND")
    print("process=TradingView.exe")
    print(f"hwnd={window.hwnd}")
    print(f"title={window.title}")
    if is_minimized(window.hwnd):
        print("VISION_WINDOW_MINIMIZED")
        return 3
    shot = capture_window(window)
    if shot is None:
        print("CAPTURE_VALID=false")
        return 4
    folder = Path("cdx_vision/debug") / f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "window.png"
    shot.image.save(path)
    print(f"CAPTURE_METHOD={shot.method}")
    print(f"SIZE={shot.image.width}x{shot.image.height}")
    print("CAPTURE_VALID=true")
    print(f"SAVED={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
