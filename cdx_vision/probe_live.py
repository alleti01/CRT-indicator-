"""Read the open TradingView chart once. Does not place an order or use a webhook."""
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
        signal_id=f"PROBE_{uuid.uuid4().hex[:8]}",
        direction="SHORT",
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=None,
    )
    result = run_shadow_job(request, VisionConfig(enabled=True, shadow_only=True, execution_enabled=False))
    print("DRY_RUN_ONLY")
    print("status", result.state.value)
    print("entry", result.entry, result.entry_source)
    print("stop", result.stop)
    print("tp1", result.tp1)
    print("tp2", result.tp2)
    print("reasons", ",".join(result.reasons))
    print("capture", result.window_bounds)
    if result.confirmed:
        return 0
    if "VISION_NO_CDX_TEXT" in result.reasons or "VISION_SL_NOT_FOUND" in result.reasons:
        print("NO_ACTIVE_CDX_LEVEL_SET")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
