"""Validate a CDX level set. Fail closed. Never invent a missing price."""
from __future__ import annotations

from decimal import Decimal

from cdx_vision.models import CDXLevelCandidate, ParsedLevel, Reason
from cdx_vision.parser import on_tick


def _near(price: Decimal, reference: Decimal | None, bound: Decimal) -> bool:
    if reference is None:
        return True
    return abs(price - reference) <= bound


def build_candidates(
    levels: list[ParsedLevel],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    tick: Decimal,
    sanity_points: Decimal,
) -> tuple[list[CDXLevelCandidate], list[str]]:
    reasons: list[str] = []
    by_label: dict[str, list[ParsedLevel]] = {}
    for level in levels:
        by_label.setdefault(level.normalized_label, []).append(level)
    for name, code in (
        ("SL", Reason.VISION_SL_NOT_FOUND),
        ("TP1", Reason.VISION_TP1_NOT_FOUND),
        ("TP2", Reason.VISION_TP2_NOT_FOUND),
    ):
        if name not in by_label:
            reasons.append(code.value)
    if reasons:
        return [], reasons

    entries = by_label.get("ENTRY", [])
    candidates: list[CDXLevelCandidate] = []
    # Pair each SL with the nearest TP1 and TP2 by vertical center.
    for stop in by_label["SL"]:
        tp1 = min(by_label["TP1"], key=lambda item: abs(item.cy - stop.cy) if hasattr(item, "cy") else abs(((item.y1 + item.y2) / 2) - ((stop.y1 + stop.y2) / 2)))
        tp2 = min(by_label["TP2"], key=lambda item: abs(((item.y1 + item.y2) / 2) - ((stop.y1 + stop.y2) / 2)))
        entry_level = None
        entry_source = "VISION"
        if entries:
            entry_level = min(entries, key=lambda item: abs(((item.y1 + item.y2) / 2) - ((stop.y1 + stop.y2) / 2)))
            entry = entry_level.price
        elif webhook_price is not None:
            entry = webhook_price
            entry_source = "WEBHOOK"
        else:
            reasons.append(Reason.VISION_ENTRY_NOT_FOUND.value)
            continue
        bundle = (stop, tp1, tp2) if entry_level is None else (entry_level, stop, tp1, tp2)
        for piece in (stop, tp1, tp2):
            if not on_tick(piece.price, tick):
                reasons.append(Reason.VISION_OFF_TICK.value)
        if not on_tick(entry, tick):
            reasons.append(Reason.VISION_OFF_TICK.value)
        ref = webhook_price or entry
        if not all(_near(piece.price, ref, sanity_points) for piece in (stop, tp1, tp2)) or not _near(entry, ref, sanity_points):
            reasons.append(Reason.VISION_SANITY_FAIL.value)
            continue
        if webhook_direction == "LONG":
            ordered = entry > stop.price and tp1.price > entry and tp2.price > tp1.price
        elif webhook_direction == "SHORT":
            ordered = stop.price > entry and entry > tp1.price and tp1.price > tp2.price
        else:
            ordered = False
        if not ordered:
            reasons.append(Reason.VISION_INVALID_ORDERING.value)
            continue
        candidates.append(
            CDXLevelCandidate(
                direction_seen=webhook_direction,
                entry=entry,
                entry_source=entry_source,
                stop=stop.price,
                tp1=tp1.price,
                tp2=tp2.price,
                levels=tuple(bundle),
            )
        )
    return candidates, reasons


def direction_conflict(webhook_direction: str, seen: str) -> bool:
    return bool(seen) and seen != webhook_direction


def ambiguous(candidates: list[CDXLevelCandidate]) -> bool:
    unique = {(c.stop, c.tp1, c.tp2) for c in candidates}
    return len(unique) > 1
