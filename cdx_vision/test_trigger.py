"""Run the shadow worker against the live chart. Does not place an order."""
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from cdx_vision.config import VisionConfig
from cdx_vision.live_job import run_shadow_job
from cdx_vision.models import VisionCaptureRequest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--side", default="SHORT")
    parser.add_argument("--price", default="")
    args = parser.parse_args()
    price = Decimal(args.price) if args.price else None
    now = datetime.now(timezone.utc)
    request = VisionCaptureRequest(
        signal_id=f"TEST_{uuid.uuid4().hex[:12]}",
        direction=args.side.upper(),
        ticker="NQ",
        webhook_received_at=now,
        webhook_price=price,
    )
    result = run_shadow_job(request, VisionConfig(enabled=True, shadow_only=True, execution_enabled=False))
    print("source=TEST")
    print("signal_id", result.signal_id)
    print("status", result.state.value)
    print("stop", result.stop)
    print("tp1", result.tp1)
    print("tp2", result.tp2)
    print("reasons", ",".join(result.reasons))
    return 0 if result.state.value in {"VISION_CONFIRMED", "VISION_REJECTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
