"""List TradingView windows and write a normalized ROI config. No credentials."""
from __future__ import annotations

import json
from pathlib import Path

from cdx_vision.window_locator import list_windows


def main() -> int:
    windows = list_windows("TradingView")
    path = Path("cdx_vision/config/windows_chart.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not windows:
        print("VISION_WINDOW_NOT_FOUND")
        return 2
    chosen = windows[0]
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
