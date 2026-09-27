"""Turn OCR tokens into one candidate level set for a single frame."""
from __future__ import annotations

from decimal import Decimal

from cdx_vision.models import CDXLevelCandidate, OCRToken, Reason
from cdx_vision.parser import parse_tokens
from cdx_vision.validator import ambiguous, build_candidates, direction_conflict


def frame_candidate(
    tokens: list[OCRToken],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    tick: Decimal,
    sanity_points: Decimal,
) -> tuple[CDXLevelCandidate | None, list[str]]:
    levels, seen = parse_tokens(tokens, tick)
    if direction_conflict(webhook_direction, seen):
        return None, [Reason.VISION_DIRECTION_CONFLICT.value]
    if not levels:
        return None, [Reason.VISION_NO_CDX_TEXT.value]
    candidates, reasons = build_candidates(
        levels,
        webhook_direction=webhook_direction,
        webhook_price=webhook_price,
        tick=tick,
        sanity_points=sanity_points,
    )
    if not candidates:
        return None, reasons or [Reason.VISION_NO_CDX_TEXT.value]
    if ambiguous(candidates):
        return None, [Reason.VISION_AMBIGUOUS_LEVEL_SET.value]
    return candidates[0], []
