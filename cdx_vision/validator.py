"""Validate a CDX level set. Fail closed. Never invent a missing price."""
from __future__ import annotations

from decimal import Decimal

from cdx_vision.models import CDXLevelCandidate, ParsedLevel, Reason
from cdx_vision.parser import on_tick


def ordered(
    direction: str,
    entry: Decimal,
    stop: Decimal,
    tp1: Decimal,
    tp2: Decimal | None = None,
) -> bool:
    """TP2 is optional. When it is present it has to sit beyond TP1."""
    if direction == "LONG":
        base = stop < entry < tp1
        return base if tp2 is None else base and tp1 < tp2
    if direction == "SHORT":
        base = stop > entry > tp1
        return base if tp2 is None else base and tp1 > tp2
    return False


def _near(price: Decimal, reference: Decimal | None, bound: Decimal) -> bool:
    if reference is None:
        return True
    return abs(price - reference) <= bound


def _candidate(
    *,
    direction: str,
    entry: Decimal,
    source: str,
    stop: ParsedLevel,
    tp1: ParsedLevel,
    tp2: ParsedLevel | None,
    visual: Decimal | None,
    webhook: Decimal | None,
    fill: Decimal | None,
    reason: str,
    unstable: bool,
) -> CDXLevelCandidate:
    bundle = tuple(level for level in (stop, tp1, tp2) if level is not None)
    return CDXLevelCandidate(
        direction_seen=direction,
        entry=entry,
        entry_source=source,
        stop=stop.price,
        tp1=tp1.price,
        tp2=None if tp2 is None else tp2.price,
        levels=bundle,
        visual_entry=visual,
        webhook_entry=webhook,
        actual_fill=fill,
        entry_unstable=unstable,
        entry_reason=reason,
    )


def build_candidates(
    levels: list[ParsedLevel],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    tick: Decimal,
    sanity_points: Decimal,
    actual_fill: Decimal | None = None,
) -> tuple[list[CDXLevelCandidate], list[str]]:
    reasons: list[str] = []
    by_label: dict[str, list[ParsedLevel]] = {}
    for level in levels:
        by_label.setdefault(level.normalized_label, []).append(level)
    for name, code in (
        ("SL", Reason.VISION_SL_NOT_FOUND),
        ("TP1", Reason.VISION_TP1_NOT_FOUND),
    ):
        if name not in by_label:
            reasons.append(code.value)
    if reasons:
        return [], reasons
    tp2_levels = by_label.get("TP2", [])

    entries = by_label.get("ENTRY", [])
    candidates: list[CDXLevelCandidate] = []
    for stop in by_label["SL"]:
        stop_x = (stop.x1 + stop.x2) / 2
        stop_y = (stop.y1 + stop.y2) / 2

        def nearest(levels: list[ParsedLevel]) -> ParsedLevel:
            return min(
                levels,
                key=lambda item: (
                    abs(((item.x1 + item.x2) / 2) - stop_x),
                    abs(((item.y1 + item.y2) / 2) - stop_y),
                ),
            )

        tp1 = nearest(by_label["TP1"])
        tp2 = nearest(tp2_levels) if tp2_levels else None
        visual = None
        recorded_visual = None
        unstable = False
        mismatch_drop = False
        if entries:
            chosen_entry = nearest(entries)
            chosen_x = (chosen_entry.x1 + chosen_entry.x2) / 2
            collided = [
                level
                for level in entries
                if level.price != chosen_entry.price and abs(((level.x1 + level.x2) / 2) - chosen_x) < 80
            ]
            if collided:
                unstable = True
            else:
                visual = chosen_entry.price
                recorded_visual = visual
                if webhook_price is not None and abs(visual - webhook_price) > sanity_points:
                    visual = None
                    mismatch_drop = True
        priced = [stop, tp1] + ([tp2] if tp2 is not None else [])
        for piece in priced:
            if not on_tick(piece.price, tick):
                reasons.append(Reason.VISION_OFF_TICK.value)
        if not all(_near(piece.price, webhook_price or visual, sanity_points) for piece in priced):
            reasons.append(Reason.VISION_SANITY_FAIL.value)
            continue

        use_visual = visual
        if use_visual is not None and not on_tick(use_visual, tick):
            use_visual = None
        tp2_price = None if tp2 is None else tp2.price
        if use_visual is not None and not ordered(webhook_direction, use_visual, stop.price, tp1.price, tp2_price):
            use_visual = None
        if use_visual is not None:
            candidates.append(
                _candidate(
                    direction=webhook_direction,
                    entry=use_visual,
                    source="VISION",
                    stop=stop,
                    tp1=tp1,
                    tp2=tp2,
                    visual=use_visual,
                    webhook=webhook_price,
                    fill=actual_fill,
                    reason="",
                    unstable=False,
                )
            )
            continue

        fallback_price = webhook_price if webhook_price is not None else actual_fill
        fallback_source = "WEBHOOK" if webhook_price is not None else ("FILL" if actual_fill is not None else "")
        if fallback_price is None or not fallback_source:
            if mismatch_drop:
                reasons.append(Reason.VISION_ENTRY_WEBHOOK_MISMATCH.value)
            elif unstable:
                reasons.append(Reason.VISION_ENTRY_UNSTABLE.value)
            reasons.append(Reason.VISION_REJECT_ENTRY_UNAVAILABLE.value)
            continue
        if not on_tick(fallback_price, tick) or not ordered(webhook_direction, fallback_price, stop.price, tp1.price, tp2_price):
            reasons.append(Reason.VISION_INVALID_ORDERING.value)
            continue
        if not _near(fallback_price, webhook_price or fallback_price, sanity_points):
            reasons.append(Reason.VISION_SANITY_FAIL.value)
            continue
        if mismatch_drop:
            reason = Reason.VISION_ENTRY_WEBHOOK_MISMATCH.value
        elif unstable:
            reason = Reason.VISION_ENTRY_UNSTABLE.value
        elif fallback_source == "WEBHOOK":
            reason = Reason.VISION_ENTRY_NOT_FOUND_WEBHOOK_FALLBACK.value
        else:
            reason = ""
        candidates.append(
            _candidate(
                direction=webhook_direction,
                entry=fallback_price,
                source=fallback_source,
                stop=stop,
                tp1=tp1,
                tp2=tp2,
                visual=recorded_visual if mismatch_drop else None,
                webhook=webhook_price,
                fill=actual_fill,
                reason=reason,
                unstable=unstable,
            )
        )
    if not candidates and Reason.VISION_REJECT_ENTRY_UNAVAILABLE.value not in reasons and not entries and webhook_price is None and actual_fill is None:
        reasons.append(Reason.VISION_REJECT_ENTRY_UNAVAILABLE.value)
    return candidates, reasons


def direction_conflict(webhook_direction: str, seen: str) -> bool:
    return bool(seen) and seen != webhook_direction


def ambiguous(candidates: list[CDXLevelCandidate]) -> bool:
    unique = {(c.stop, c.tp1, c.tp2) for c in candidates}
    return len(unique) > 1
