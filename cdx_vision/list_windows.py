"""List visible TradingView desktop app windows. Browsers are not included."""
from __future__ import annotations

from cdx_vision.window_locator import list_tradingview_windows


def main() -> int:
    windows = list_tradingview_windows()
    if not windows:
        print("VISION_WINDOW_NOT_FOUND")
        return 2
    for index, window in enumerate(windows, start=1):
        print(f"[{index}]")
        print(f"hwnd={window.hwnd}")
        print("process=TradingView.exe")
        print(f"title={window.title}")
        print(f"bounds={window.left},{window.top},{window.right},{window.bottom}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
