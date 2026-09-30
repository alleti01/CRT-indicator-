"""Choose auto-right only when the current trade is actually off screen."""
from __future__ import annotations

from cdx_vision.models import OCRToken


def current_signal_visible(tokens: list[OCRToken]) -> bool:
    """A CDX LONG/SHORT marker in this capture. OCR failure is not off-screen."""
    blob = " ".join(token.text.upper() for token in tokens)
    has_side = "LONG" in blob or "SHORT" in blob
    return "CDX" in blob and has_side


def extraction_route(*, levels_visible: bool, marker_visible: bool) -> str:
    if levels_visible:
        return "READY"
    if marker_visible:
        return "VISIBLE_EXTRACTION"
    return "AUTO_RIGHT"
