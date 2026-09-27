"""Turn OCR tokens into one candidate level set for a single frame."""
from __future__ import annotations

from decimal import Decimal

from cdx_vision.active_trade_selector import select_active
from cdx_vision.models import CDXLevelCandidate, OCRToken, Reason
from cdx_vision.parser import normalize_label, parse_tokens
from cdx_vision.validator import build_candidates


def frame_candidate(
    tokens: list[OCRToken],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    tick: Decimal,
    sanity_points: Decimal,
    actual_fill: Decimal | None = None,
) -> tuple[CDXLevelCandidate | None, list[str]]:
    levels, _seen = parse_tokens(tokens, tick)
    if not levels:
        return None, [Reason.VISION_NO_CDX_TEXT.value]
    candidates, reasons = build_candidates(
        levels,
        webhook_direction=webhook_direction,
        webhook_price=webhook_price,
        tick=tick,
        sanity_points=sanity_points,
        actual_fill=actual_fill,
    )
    if not candidates:
        labels = {normalize_label(token.text) for token in tokens}
        if webhook_direction == "SHORT" and "LONG" in labels and "SHORT" not in labels:
            return None, [Reason.VISION_DIRECTION_CONFLICT.value]
        if webhook_direction == "LONG" and "SHORT" in labels and "LONG" not in labels:
            return None, [Reason.VISION_DIRECTION_CONFLICT.value]
        return None, reasons or [Reason.VISION_NO_CDX_TEXT.value]
    chosen, select_reasons, _verdicts = select_active(
        candidates,
        tokens,
        webhook_direction=webhook_direction,
        webhook_price=webhook_price,
        sanity_points=sanity_points,
    )
    if chosen is None:
        return None, select_reasons or reasons
    return chosen, []
