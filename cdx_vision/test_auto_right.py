"""Pan the TradingView chart right only when the current CDX trade is off screen.

Does not place an order. Ctrl+Right is sent only to a foreground TradingView window.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from cdx_vision.config import VisionConfig
from cdx_vision.live_job import run_shadow_job
from cdx_vision.models import VisionCaptureRequest


def main() -> int:
    now = datetime.now(timezone.utc)
    request = VisionCaptureRequest(
        signal_id=f"AUTORIGHT_{uuid.uuid4().hex[:8]}",
        direction="SHORT",
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=None,
    )
    config = VisionConfig(
        enabled=True,
        shadow_only=True,
        execution_enabled=False,
        auto_right_enabled=True,
        auto_right_max_attempts=3,
        redraw_delay_ms=400,
    )
    result = run_shadow_job(request, config)
    print("BEFORE_LEVELS_VISIBLE=" + ("true" if result.initial_levels_visible else "false"))
    print("NAVIGATION_ATTEMPTS=" + str(result.auto_right_attempts))
    print("AFTER_LEVELS_VISIBLE=" + ("true" if result.auto_right_success or result.initial_levels_visible else "false"))
    print("REASON", result.navigation_reason or ",".join(result.reasons))
    print("status", result.state.value)
    print("ORDERS", config.may_route_orders())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
