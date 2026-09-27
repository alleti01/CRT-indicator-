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
from cdx_vision.service import VisionBridge

log = logging.getLogger("cdx_vision.shadow")
_bridge: VisionBridge | None = None


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
    global _bridge
    try:
        if _bridge is None:
            _bridge = VisionBridge(config)
        from cdx_vision.window_locator import list_tradingview_windows

        windows = list_tradingview_windows()
        if not windows:
            _bridge.process_frames(request, [], window_title="")
            return
        _bridge.process_frames(request, [], window_title=windows[0].title)
    except Exception:
        log.exception("cdx vision shadow failed signal_id=%s", request.signal_id)
