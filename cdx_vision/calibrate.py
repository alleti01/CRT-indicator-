"""Save the TradingView desktop app as the only capture target."""
from __future__ import annotations

import json
from pathlib import Path

from cdx_vision.window_locator import list_tradingview_windows


def main() -> int:
    windows = list_tradingview_windows()
    path = Path("cdx_vision/config/windows_chart.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(windows) == 0:
        print("VISION_WINDOW_NOT_FOUND")
        return 2
    if len(windows) > 1:
        print("AMBIGUOUS")
        for window in windows:
            print(window.title)
        return 3
    chosen = windows[0]
    payload = {
        "process_name": "TradingView.exe",
        "window_title": chosen.title,
        "bounds": [chosen.left, chosen.top, chosen.right, chosen.bottom],
        "chart_roi": [0.05, 0.08, 0.82, 0.92],
        "ocr_roi": [0.15, 0.10, 0.80, 0.90],
        "note": "Capture is limited to the TradingView desktop app. ROIs are fractions of that window.",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"saved {path}")
    print(f"process=TradingView.exe title={chosen.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
