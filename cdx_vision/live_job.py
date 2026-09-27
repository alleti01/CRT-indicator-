"""Webhook-triggered shadow job. Captures only the TradingView app."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from cdx_vision.config import VisionConfig
from cdx_vision.consensus import consensus
from cdx_vision.entry_read import read_visual_entry
from cdx_vision.levels import frame_candidate
from cdx_vision.models import Reason, VisionCaptureRequest, VisionState
from cdx_vision.ocr import TesseractOcr, chart_crop, preprocess
from cdx_vision.screen_capture import capture_window, is_minimized
from cdx_vision.service import VisionBridge
from cdx_vision.tesseract_cmd import resolve_tesseract
from cdx_vision.window_locator import list_tradingview_windows

log = logging.getLogger("cdx_vision.live")
_DELAYS = (0.0, 0.25, 0.5, 1.0)


def load_roi() -> tuple[float, float, float, float]:
    path = Path("cdx_vision/config/windows_chart.json")
    if not path.exists():
        return (0.15, 0.10, 0.80, 0.90)
    data = json.loads(path.read_text(encoding="utf-8"))
    roi = data.get("ocr_roi") or [0.15, 0.10, 0.80, 0.90]
    return tuple(float(v) for v in roi)  # type: ignore[return-value]


def run_shadow_job(
    request: VisionCaptureRequest,
    config: VisionConfig | None = None,
    debug_dir: Path | None = None,
) -> object:
    """Capture, OCR, validate, and append a ledger row. Never places an order."""
    config = config or VisionConfig(enabled=True, shadow_only=True, execution_enabled=False)
    bridge = VisionBridge(config)
    windows = list_tradingview_windows()
    now = datetime.now(timezone.utc)
    if not windows:
        return bridge.process_frames(request, [], now=now, window_title="")
    window = windows[0]
    if is_minimized(window.hwnd):
        result = bridge.process_frames(request, [], now=now, window_title=window.title)
        result.reasons = [Reason.VISION_WINDOW_MINIMIZED.value]
        result.state = VisionState.VISION_REJECTED
        return result
    exe = resolve_tesseract()
    if not exe:
        return bridge.process_frames(request, [], now=now, window_title=window.title)
    engine = TesseractOcr(exe, psm=11)
    roi = load_roi()
    frames = []
    method = ""
    entry_raw: list[str] = []
    started = time.perf_counter()
    for delay in _DELAYS:
        if delay:
            time.sleep(delay)
        if (time.perf_counter() - started) > config.timeout_seconds:
            break
        shot = capture_window(window)
        if shot is None:
            continue
        method = shot.method
        crop = chart_crop(shot.image, roi)
        tokens = list(engine.recognize(preprocess(crop, scale=3)))
        observed = read_visual_entry(
            engine,
            shot.image,
            roi,
            tokens,
            scale=3,
            debug_dir=debug_dir if not frames else None,
        )
        tokens.extend(observed.tokens)
        entry_raw.extend(observed.raw)
        frames.append(tokens)
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
        chosen, _reasons, _unstable = consensus(parsed)
        if chosen is not None:
            break
    result = bridge.process_frames(
        request,
        frames,
        now=datetime.now(timezone.utc),
        window_title=window.title,
        window_bounds=method or "NONE",
    )
    result.entry_raw = " | ".join(entry_raw)
    result.window_bounds = method or "NONE"
    if not frames:
        result.reasons = [Reason.VISION_CAPTURE_INVALID.value]
        result.state = VisionState.VISION_REJECTED
    return result
