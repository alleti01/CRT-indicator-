"""Webhook-triggered shadow job. Captures only the TradingView app."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from cdx_vision.active_trade_selector import should_navigate
from cdx_vision.auto_right import ChartNavigator, run_navigation
from cdx_vision.config import VisionConfig
from cdx_vision.consensus import consensus
from cdx_vision.entry_read import read_visual_entry
from cdx_vision.levels import frame_candidate
from cdx_vision.models import Reason, VisionCaptureRequest, VisionState
from cdx_vision.ocr import TesseractOcr, chart_crop, preprocess
from cdx_vision.screen_capture import capture_window, is_minimized
from cdx_vision.service import VisionBridge
from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.visible_levels import assemble, read_visible_tags, save_debug
from cdx_vision.visible_route import current_signal_visible, extraction_route
from cdx_vision.window_locator import list_tradingview_windows

log = logging.getLogger("cdx_vision.live")
_DELAYS = (0.25, 0.5, 1.0)


def load_roi() -> tuple[float, float, float, float]:
    path = Path("cdx_vision/config/windows_chart.json")
    if not path.exists():
        return (0.18, 0.10, 0.78, 0.88)
    data = json.loads(path.read_text(encoding="utf-8"))
    roi = data.get("ocr_roi") or [0.15, 0.10, 0.80, 0.90]
    return tuple(float(v) for v in roi)  # type: ignore[return-value]


def run_shadow_job(
    request: VisionCaptureRequest,
    config: VisionConfig | None = None,
    debug_dir: Path | None = None,
    navigator: ChartNavigator | None = None,
) -> object:
    """Capture, OCR, validate, and append a ledger row. Never places an order."""
    config = config or VisionConfig(enabled=True, shadow_only=True, execution_enabled=False)
    bridge = VisionBridge(config)
    job_started = datetime.now(timezone.utc)
    windows = list_tradingview_windows()
    if not windows:
        return bridge.process_frames(
            request,
            [],
            now=job_started,
            window_title="",
            auto_right_enabled=config.auto_right_enabled,
        )
    window = windows[0]
    if is_minimized(window.hwnd):
        return bridge.process_frames(
            request,
            [],
            now=job_started,
            window_title=window.title,
            forced_reasons=[Reason.VISION_TRADINGVIEW_MINIMIZED.value],
            auto_right_enabled=config.auto_right_enabled,
            navigation_reason=Reason.VISION_TRADINGVIEW_MINIMIZED.value,
        )
    exe = resolve_tesseract()
    if not exe:
        return bridge.process_frames(request, [], now=job_started, window_title=window.title)
    engine = TesseractOcr(exe, psm=11)
    roi = load_roi()
    method = ""
    entry_raw: list[str] = []
    nav_shots = {"n": 0}
    last_fp: dict[str, list[int] | None] = {"value": None}

    def capture(label: str = ""):
        nonlocal method
        shot = capture_window(window)
        if shot is None:
            return [], False, [], True
        method = shot.method
        fingerprint = _fingerprint(shot.image)
        moved = _moved(last_fp["value"], fingerprint)
        last_fp["value"] = fingerprint
        if debug_dir is not None and label:
            debug_dir.mkdir(parents=True, exist_ok=True)
            shot.image.save(debug_dir / label)
        crop = chart_crop(shot.image, roi)
        tokens = list(engine.recognize(preprocess(crop, scale=3)))
        observed = read_visual_entry(
            engine,
            shot.image,
            roi,
            tokens,
            scale=3,
            debug_dir=debug_dir if label in {"", "before_navigation.png"} and not entry_raw else None,
        )
        tokens.extend(observed.tokens)
        candidate, _reasons = frame_candidate(
            tokens,
            webhook_direction=request.direction,
            webhook_price=request.webhook_price,
            tick=config.tick,
            sanity_points=config.sanity_points,
            actual_fill=request.actual_fill,
        )
        return tokens, candidate is not None, observed.raw, moved

    tokens, visible, raw, _moved_first = capture("before_navigation.png" if debug_dir else "")
    entry_raw.extend(raw)
    frames: list = []
    fail_reasons: list[str] = []
    triggered = False
    attempts = 0
    success = False
    nav_reason = ""
    if visible:
        nav_reason = Reason.VISION_INITIAL_LEVELS_VISIBLE.value
        frames.append(tokens)
        started = time.perf_counter()
        for delay in _DELAYS:
            if (time.perf_counter() - started) > config.timeout_seconds:
                break
            time.sleep(delay)
            more, _vis, more_raw, _moved_more = capture()
            entry_raw.extend(more_raw)
            if more:
                frames.append(more)
            parsed = [
                frame_candidate(
                    frame,
                    webhook_direction=request.direction,
                    webhook_price=request.webhook_price,
                    tick=config.tick,
                    sanity_points=config.sanity_points,
                    actual_fill=request.actual_fill,
                )[0]
                for frame in frames
            ]
            if consensus(parsed)[0] is not None:
                break
    elif extraction_route(levels_visible=False, marker_visible=current_signal_visible(tokens)) == "VISIBLE_EXTRACTION":
        triggered = False
        nav_reason = Reason.VISION_ALREADY_AT_LIVE_EDGE.value
        frames, extra_reasons = _visible_frames(window, request, engine)
        if not frames:
            nav_reason = extra_reasons[0] if extra_reasons else nav_reason
            fail_reasons = extra_reasons or [nav_reason]
    elif config.auto_right_enabled and should_navigate(_reasons_for(tokens, request, config)):
        triggered = True
        navigator = navigator or ChartNavigator(config.chart_focus_x, config.chart_focus_y)

        def read_once():
            nav_shots["n"] += 1
            got, vis, got_raw, moved = capture(f"after_right_{nav_shots['n']}.png")
            entry_raw.extend(got_raw)
            return got, vis, moved

        state = run_navigation(
            window=window,
            initial_tokens=tokens,
            initial_visible=False,
            read_once=read_once,
            navigator=navigator,
            max_attempts=config.auto_right_max_attempts,
            redraw_s=config.redraw_delay_ms / 1000,
        )
        frames = state.frames
        attempts = state.attempts
        success = state.success
        nav_reason = state.reason
        if state.reason == "VISION_AUTO_RIGHT_NO_MOVEMENT":
            nav_reason = Reason.VISION_ALREADY_AT_LIVE_EDGE.value
            frames, extra_reasons = _visible_frames(window, request, engine)
            success = bool(frames)
            if not frames:
                fail_reasons = [nav_reason, *extra_reasons]
        elif not success and state.reason == "VISION_AUTO_RIGHT_EXHAUSTED":
            nav_reason = Reason.VISION_LEVELS_NOT_VISIBLE_AFTER_NAVIGATION.value
    else:
        if tokens:
            frames.append(tokens)
        nav_reason = Reason.VISION_LEVELS_NOT_VISIBLE.value
    result = bridge.process_frames(
        request,
        frames,
        now=job_started,
        window_title=window.title,
        window_bounds=method or "NONE",
        initial_levels_visible=visible or bool(frames),
        auto_right_enabled=config.auto_right_enabled,
        auto_right_triggered=triggered,
        auto_right_attempts=attempts,
        auto_right_success=success,
        navigation_reason=nav_reason,
        forced_reasons=fail_reasons or ([nav_reason] if triggered and not success and nav_reason else None),
    )
    if triggered and hasattr(navigator, "reset_chart_view"):
        navigator.reset_chart_view(window)
    result.entry_raw = " | ".join(entry_raw)
    result.window_bounds = method or "NONE"
    if not frames and not result.reasons:
        result.reasons = [Reason.VISION_CAPTURE_INVALID.value]
        result.state = VisionState.VISION_REJECTED
    return result


def _visible_frames(window, request: VisionCaptureRequest, engine) -> tuple[list, list[str]]:
    """Two settled frames. Empty when the visible chart does not yield a quartet."""
    reads = []
    images = []
    for index in range(2):
        shot = capture_window(window)
        if shot is None:
            return [], [Reason.VISION_CAPTURE_INVALID.value]
        tags, lines = read_visible_tags(shot.image, engine)
        read = assemble(tags, direction=request.direction, webhook_price=request.webhook_price)
        read.lines = lines
        read.tags = tags
        images.append(shot.image)
        reads.append(read)
        if index == 0 and (read.reasons or not read.tokens):
            safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in request.signal_id) or "signal"
            try:
                save_debug(
                    Path("cdx_vision/debug") / safe_id,
                    shot.image,
                    read,
                    {"signal_id": request.signal_id, "symbol": request.ticker, "side": request.direction, "live_edge": True},
                )
            except OSError:
                log.exception("vision debug folder skipped signal_id=%s", request.signal_id)
            return [], read.reasons or [Reason.VISION_TP1_NOT_FOUND.value]
        if index == 0:
            time.sleep(0.35)
    first, second = reads
    if (first.stop, first.tp1, first.tp2, first.entry) != (second.stop, second.tp1, second.tp2, second.entry):
        return [], [Reason.VISION_NO_CONSENSUS.value]
    return [first.tokens, second.tokens], []


def _fingerprint(image) -> list[int]:
    small = image.convert("L").resize((48, 27))
    return list(small.getdata())


def _moved(previous: list[int] | None, current: list[int]) -> bool:
    if previous is None or len(previous) != len(current):
        return True
    delta = sum(abs(a - b) for a, b in zip(previous, current)) / len(current)
    return delta > 4.0


def _reasons_for(tokens, request: VisionCaptureRequest, config: VisionConfig) -> list[str]:
    _candidate, reasons = frame_candidate(
        tokens,
        webhook_direction=request.direction,
        webhook_price=request.webhook_price,
        tick=config.tick,
        sanity_points=config.sanity_points,
        actual_fill=request.actual_fill,
    )
    return reasons
