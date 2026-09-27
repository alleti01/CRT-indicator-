"""Read the open TradingView chart once. Does not place an order or use a webhook."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.ledger import level_metrics
from cdx_vision.live_job import run_shadow_job
from cdx_vision.models import VisionCaptureRequest


def main() -> int:
    now = datetime.now().astimezone()
    debug = Path("cdx_vision/debug") / f"manual_{now.strftime('%Y%m%d_%H%M%S')}"
    request = VisionCaptureRequest(
        signal_id=f"PROBE_{uuid.uuid4().hex[:8]}",
        direction="SHORT",
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=None,
    )
    result = run_shadow_job(
        request,
        VisionConfig(enabled=True, shadow_only=True, execution_enabled=False),
        debug_dir=debug,
    )
    stats = level_metrics(result)
    print("DRY_RUN_ONLY")
    print("VISION ENTRY:")
    print("   ", result.visual_entry if result.visual_entry is not None else "NOT FOUND")
    print("WEBHOOK ENTRY:")
    print("   ", result.webhook_entry if result.webhook_entry is not None else "N/A")
    print("ACTIVE ENTRY SOURCE:")
    print("   ", result.entry_source or "MISSING")
    print("SL:")
    print("   ", result.stop if result.stop is not None else "NOT FOUND")
    print("TP1:")
    print("   ", result.tp1 if result.tp1 is not None else "NOT FOUND")
    print("TP2:")
    print("   ", result.tp2 if result.tp2 is not None else "NOT FOUND")
    print("GEOMETRY:")
    print("   ", result.state.value)
    print("R:")
    print("   ", stats["native_r_points"], stats["native_r_source"])
    print("TP1_R:", stats["tp1_R"])
    print("TP2_R:", stats["tp2_R"])
    print("RAW ENTRY:")
    print("   ", result.entry_raw or "none")
    print("reasons", ",".join(result.reasons))
    print("capture", result.window_bounds)
    if result.confirmed and result.entry_source == "VISION":
        return 0
    if result.confirmed:
        print("WEBHOOK_FALLBACK")
        return 0
    if any(code in result.reasons for code in ("VISION_NO_CDX_TEXT", "VISION_SL_NOT_FOUND", "VISION_REJECT_ENTRY_UNAVAILABLE")):
        print("NO_ACTIVE_CDX_LEVEL_SET")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
