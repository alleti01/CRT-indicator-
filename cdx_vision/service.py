"""Shadow vision session. Never places or changes an order."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from cdx_vision.config import VisionConfig
from cdx_vision.consensus import consensus
from cdx_vision.ledger import VisionLedger
from cdx_vision.levels import frame_candidate
from cdx_vision.models import OCRToken, Reason, VisionCaptureRequest, VisionResult, VisionState

log = logging.getLogger("cdx_vision.service")


class VisionBridge:
    def __init__(self, config: VisionConfig | None = None, ledger: VisionLedger | None = None) -> None:
        self.config = config or VisionConfig.from_env()
        self.ledger = ledger or VisionLedger(self.config.ledger_path, self.config.research_csv)
        self.started_at = datetime.now(timezone.utc)
        self._done: dict[str, VisionResult] = {}
        self._transitions: list[tuple[str, str, str]] = []

    def may_route_orders(self) -> bool:
        return self.config.may_route_orders()

    def _transition(self, signal_id: str, state: VisionState) -> None:
        self._transitions.append((signal_id, state.value, datetime.now(timezone.utc).isoformat()))
        log.info("vision state signal_id=%s state=%s", signal_id, state.value)

    def process_frames(
        self,
        request: VisionCaptureRequest,
        frames: list[list[OCRToken]],
        *,
        now: datetime | None = None,
        window_title: str = "",
        window_bounds: str = "",
        forced_reasons: list[str] | None = None,
        initial_levels_visible: bool = False,
        auto_right_enabled: bool = False,
        auto_right_triggered: bool = False,
        auto_right_attempts: int = 0,
        auto_right_success: bool = False,
        navigation_reason: str = "",
    ) -> VisionResult:
        now = now or datetime.now(timezone.utc)
        if request.signal_id in self._done:
            prior = self._done[request.signal_id]
            prior.reasons = list(dict.fromkeys([*prior.reasons, Reason.VISION_DUPLICATE.value]))
            log.info("vision duplicate signal_id=%s", request.signal_id)
            return prior
        result = VisionResult(
            signal_id=request.signal_id,
            state=VisionState.IDLE,
            direction=request.direction,
            webhook_received_at=request.webhook_received_at,
            webhook_entry=request.webhook_price,
            actual_fill=request.actual_fill,
            entry_source="MISSING",
            initial_levels_visible=initial_levels_visible,
            auto_right_enabled=auto_right_enabled,
            auto_right_triggered=auto_right_triggered,
            auto_right_attempts=auto_right_attempts,
            auto_right_success=auto_right_success,
            navigation_reason=navigation_reason,
        )
        self._transition(request.signal_id, VisionState.CAPTURE_REQUESTED)
        if not self.config.enabled:
            return self._finish(request, result, VisionState.VISION_REJECTED, [Reason.VISION_DISABLED.value], now)
        age = (now - request.webhook_received_at).total_seconds()
        if request.webhook_received_at < self.started_at - timedelta(seconds=1):
            return self._finish(request, result, VisionState.VISION_REJECTED, [Reason.VISION_REJECT_RESTART_STALE.value], now)
        if age > self.config.timeout_seconds:
            return self._finish(request, result, VisionState.VISION_TIMEOUT, [Reason.VISION_TIMEOUT.value], now)
        if forced_reasons:
            return self._finish(request, result, VisionState.VISION_REJECTED, forced_reasons, now)
        if self.config.require_tradingview_visible and not window_title and not frames:
            return self._finish(request, result, VisionState.VISION_REJECTED, [Reason.VISION_WINDOW_NOT_FOUND.value], now)

        self._transition(request.signal_id, VisionState.CAPTURING)
        result.capture_started_at = now
        result.frame_count = len(frames)
        result.window_title = window_title
        result.window_bounds = window_bounds
        self._transition(request.signal_id, VisionState.PARSING)
        parsed = []
        parse_reasons: list[str] = []
        for frame in frames:
            candidate, reasons = frame_candidate(
                frame,
                webhook_direction=request.direction,
                webhook_price=request.webhook_price,
                tick=self.config.tick,
                sanity_points=self.config.sanity_points,
                actual_fill=request.actual_fill,
            )
            parsed.append(candidate)
            parse_reasons.extend(reasons)
        self._transition(request.signal_id, VisionState.VALIDATING)
        self._transition(request.signal_id, VisionState.CONSENSUS_PENDING)
        chosen, reasons, unstable = consensus(parsed)
        result.ocr_unstable = unstable
        if unstable:
            reasons = list(dict.fromkeys([*reasons, Reason.VISION_OCR_UNSTABLE.value]))
        if chosen is None:
            fail = list(dict.fromkeys([*reasons, *parse_reasons])) or [Reason.VISION_NO_CONSENSUS.value]
            state = VisionState.VISION_TIMEOUT if Reason.VISION_TIMEOUT.value in fail else VisionState.VISION_REJECTED
            return self._finish(request, result, state, fail, now)
        if self.config.require_consensus:
            result.agreeing_frame_count = 2
        result.entry = chosen.entry
        result.native_entry = chosen.entry
        result.entry_source = chosen.entry_source
        result.visual_entry = chosen.visual_entry
        result.webhook_entry = request.webhook_price
        result.actual_fill = request.actual_fill
        result.stop = chosen.stop
        result.tp1 = chosen.tp1
        result.tp2 = chosen.tp2
        if (
            chosen.visual_entry is not None
            and request.webhook_price is not None
            and abs(chosen.visual_entry - request.webhook_price) > self.config.entry_mismatch_points
        ):
            reasons = list(dict.fromkeys([*reasons, Reason.VISION_ENTRY_WEBHOOK_MISMATCH.value]))
        return self._finish(request, result, VisionState.VISION_CONFIRMED, reasons, now)

    def _finish(self, request: VisionCaptureRequest, result: VisionResult, state: VisionState, reasons: list[str], now: datetime) -> VisionResult:
        result.state = state
        result.reasons = list(dict.fromkeys(reasons))
        result.confirmed_at = now
        self._transition(request.signal_id, state)
        self._done[request.signal_id] = result
        if self.config.shadow_only or not self.may_route_orders():
            self.ledger.append(result, ticker=request.ticker)
        return result
