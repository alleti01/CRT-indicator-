"""Two consecutive identical reads confirm a level set. A 2-1 vote does not."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cdx_vision.models import CDXLevelCandidate, Reason
from cdx_vision.validator import ordered


def _levels(candidate: CDXLevelCandidate) -> tuple:
    return (candidate.stop, candidate.tp1, candidate.tp2)


def _visual(candidate: CDXLevelCandidate) -> Decimal | None:
    if candidate.entry_unstable:
        return None
    if candidate.entry_source == "VISION":
        return candidate.visual_entry if candidate.visual_entry is not None else candidate.entry
    return None


def _fallback(candidate: CDXLevelCandidate) -> CDXLevelCandidate | None:
    if candidate.webhook_entry is not None:
        price = candidate.webhook_entry
        source = "WEBHOOK"
    elif candidate.actual_fill is not None:
        price = candidate.actual_fill
        source = "FILL"
    else:
        return None
    if not ordered(candidate.direction_seen, price, candidate.stop, candidate.tp1, candidate.tp2):
        return None
    return replace(
        candidate,
        entry=price,
        entry_source=source,
        visual_entry=None,
        entry_unstable=True,
        entry_reason=Reason.VISION_ENTRY_UNSTABLE.value,
    )


def consensus(frames: list[CDXLevelCandidate | None]) -> tuple[CDXLevelCandidate | None, list[str], bool]:
    """Return candidate, reasons, ocr_unstable.

    SL, TP1, and TP2 must match on two consecutive frames.
    A visual entry is used only when those same two frames agree on it exactly.
    """
    present = [frame for frame in frames if frame is not None]
    if len(present) < 2:
        return None, [Reason.VISION_NO_CONSENSUS.value], False
    saw_level_match = False
    for left, right in zip(present, present[1:]):
        if _levels(left) != _levels(right):
            continue
        saw_level_match = True
        left_visual = _visual(left)
        right_visual = _visual(right)
        if left_visual is not None and left_visual == right_visual:
            reasons = [Reason.VISION_CONFIRMED.value]
            if left.entry_reason:
                reasons.append(left.entry_reason)
            return left, reasons, False
        if (
            left_visual is None
            and right_visual is None
            and left.entry == right.entry
            and left.entry_source == right.entry_source
            and left.entry_source in {"WEBHOOK", "FILL"}
        ):
            reasons = [Reason.VISION_CONFIRMED.value]
            if left.entry_unstable or right.entry_unstable or left.entry_reason == Reason.VISION_ENTRY_UNSTABLE.value:
                reasons.append(Reason.VISION_ENTRY_UNSTABLE.value)
            elif left.entry_reason:
                reasons.append(left.entry_reason)
            elif left.entry_source == "WEBHOOK":
                reasons.append(Reason.VISION_ENTRY_NOT_FOUND_WEBHOOK_FALLBACK.value)
            return left, list(dict.fromkeys(reasons)), False
        fallback = _fallback(left)
        other = _fallback(right)
        if fallback is not None and other is not None and fallback.entry == other.entry and fallback.entry_source == other.entry_source:
            return fallback, [Reason.VISION_CONFIRMED.value, Reason.VISION_ENTRY_UNSTABLE.value], False
    counts: dict[tuple, int] = {}
    for frame in present:
        key = _levels(frame)
        counts[key] = counts.get(key, 0) + 1
    unstable = max(counts.values()) >= 2 if counts else False
    reasons = [Reason.VISION_NO_CONSENSUS.value]
    if saw_level_match:
        reasons.append(Reason.VISION_ENTRY_UNSTABLE.value)
    return None, reasons, unstable
