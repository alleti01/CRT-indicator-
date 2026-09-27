"""Shadow status. No order controls."""
from __future__ import annotations

import json
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.window_locator import list_tradingview_windows


def main() -> int:
    config = VisionConfig.from_env()
    print("enabled", config.enabled)
    print("shadow_only", config.shadow_only)
    print("execution_enabled", config.execution_enabled)
    print("ORDERS", config.may_route_orders())
    print("OCR", "PASS" if resolve_tesseract() else "FAIL")
    windows = list_tradingview_windows()
    print("WINDOW", "FOUND" if windows else "NOT_FOUND")
    if windows:
        print("process=TradingView.exe")
        print("title", windows[0].title)
    path = Path("cdx_vision/logs/vision_levels.jsonl")
    if path.exists() and path.stat().st_size:
        last = json.loads(path.read_text(encoding="utf-8").splitlines()[-1])
        print("latest_signal", last.get("signal_id"))
        print("latest_status", last.get("validation_status"))
        print("entry", last.get("entry"))
        print("stop", last.get("stop"))
        print("tp1", last.get("tp1"))
        print("tp2", last.get("tp2"))
    print("MODE", "SHADOW_ONLY" if config.shadow_only and not config.may_route_orders() else "BLOCKED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
