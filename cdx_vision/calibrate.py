"""List chart windows and save a normalized ROI. Does not guess among several browsers."""
from __future__ import annotations

import json
from pathlib import Path

from cdx_vision.window_locator import list_browser_windows, list_windows


def main() -> int:
    titled = list_windows("TradingView")
    path = Path("cdx_vision/config/windows_chart.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(titled) == 1:
        chosen = titled[0]
    elif len(titled) > 1:
        print("AMBIGUOUS")
        for window in titled:
            print(window.title)
        return 3
    else:
        browsers = list_browser_windows()
        print("CALIBRATION_PENDING_TRADINGVIEW")
        for window in browsers:
            print(window.title)
        return 2
    payload = {
        "window_title_pattern": "TradingView",
        "window_title": chosen.title,
        "bounds": [chosen.left, chosen.top, chosen.right, chosen.bottom],
        "chart_roi": [0.05, 0.08, 0.82, 0.92],
        "ocr_roi": [0.15, 0.10, 0.80, 0.90],
        "note": "ROIs are fractions of the window, not raw pixels.",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"saved {path} title={chosen.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
