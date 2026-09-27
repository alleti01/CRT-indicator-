"""Pan the TradingView chart right only when the current CDX trade is off screen.

Does not place an order. Ctrl+Right is sent only to a foreground TradingView window.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.live_job import run_shadow_job
from cdx_vision.models import VisionCaptureRequest


def main() -> int:
    now = datetime.now(timezone.utc)
    request = VisionCaptureRequest(
        signal_id=f"TEST_AUTORIGHT_{uuid.uuid4().hex[:8]}",
        direction="SHORT",
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=Decimal("30909.50"),
    )
    config = VisionConfig(
        enabled=True,
        shadow_only=True,
        execution_enabled=False,
        auto_right_enabled=True,
        auto_right_max_attempts=3,
        redraw_delay_ms=500,
    )
    debug = Path("cdx_vision/debug") / f"autoright_{now.strftime('%H%M%S')}"
    result = run_shadow_job(request, config, debug_dir=debug)
    print("source=TEST")
    print("BEFORE_LEVELS_VISIBLE=" + ("true" if result.initial_levels_visible else "false"))
    print("AUTO_RIGHT_TRIGGERED=" + ("true" if result.auto_right_triggered else "false"))
    print("AUTO_RIGHT_ATTEMPTS=" + str(result.auto_right_attempts))
    found = result.auto_right_success or (result.initial_levels_visible and result.confirmed)
    print("LEVELS_FOUND_AFTER_RIGHT_NAVIGATION=" + ("true" if result.auto_right_success else "false"))
    print("ENTRY", result.visual_entry if result.visual_entry is not None else result.entry)
    print("ENTRY_SOURCE", result.entry_source or "N/A")
    print("SL", result.stop)
    print("TP1", result.tp1)
    print("TP2", result.tp2)
    print("TWO_FRAME_CONSENSUS", "PASS" if result.confirmed else "FAIL")
    print("EXECUTION_CALLS", 0 if not config.may_route_orders() else 1)
    print("REASON", result.navigation_reason or ",".join(result.reasons))
    print("status", result.state.value)
    print("DEBUG", debug)
    return 0 if found and result.confirmed else 1


if __name__ == "__main__":
    raise SystemExit(main())
