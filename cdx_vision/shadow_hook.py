"""Enqueue a shadow capture after the webhook has already been accepted.

This module has no order client. CDX_VISION_ENABLED defaults to false.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from threading import Thread

from cdx_vision.config import VisionConfig
from cdx_vision.models import VisionCaptureRequest

log = logging.getLogger("cdx_vision.shadow")


def enqueue_shadow(signal, received_at: datetime | None = None) -> None:
    config = VisionConfig.from_env()
    if not config.enabled:
        return
    if config.may_route_orders():
        log.error("vision order routing is disabled in this build")
        return
    received_at = received_at or datetime.now(timezone.utc)
    price = Decimal(str(signal.signal_price)) if signal.signal_price else None
    request = VisionCaptureRequest(
        signal_id=signal.signal_id,
        direction=signal.direction,
        ticker=signal.symbol or "NQ",
        webhook_received_at=received_at,
        webhook_price=price,
    )
    Thread(target=_run, args=(config, request), daemon=True, name="cdx-vision-shadow").start()


def _run(config: VisionConfig, request: VisionCaptureRequest) -> None:
    try:
        from cdx_vision.live_job import run_shadow_job

        log.info("CDX_VISION_WORKER_STARTED signal_id=%s", request.signal_id)
        run_shadow_job(request, config)
    except Exception:
        log.exception("cdx vision shadow failed signal_id=%s", request.signal_id)
