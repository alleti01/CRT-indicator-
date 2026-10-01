"""Choose auto-right only when the current trade is actually off screen."""
from __future__ import annotations

from cdx_vision.models import OCRToken


def current_signal_visible(tokens: list[OCRToken]) -> bool:
    """A CDX LONG/SHORT marker in this capture. OCR failure is not off-screen."""
    blob = " ".join(token.text.upper() for token in tokens)
    has_side = "LONG" in blob or "SHORT" in blob
    return "CDX" in blob and has_side


def extraction_route(
    *,
    levels_visible: bool,
    marker_visible: bool,
    timeframe_ok: bool = True,
    live_edge: bool = False,
    offscreen: bool = False,
) -> str:
    """A visible CDX LONG/SHORT marker does not stop recovery."""
    del marker_visible
    if not timeframe_ok:
        return "RESTORE_TIMEFRAME"
    if levels_visible:
        return "READY"
    if live_edge:
        return "NATIVE_LABELS_MISSING"
    if offscreen:
        return "AUTO_RIGHT"
    return "DIAGNOSTIC_RIGHT"
