"""Pick the current CDX trade. Historical boxes are not the webhook trade."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cdx_vision.models import CDXLevelCandidate, OCRToken, Reason
from cdx_vision.parser import normalize_label

# Fraction of the OCR crop width. The crop's right edge is the current-bar side.
STALE_X_FRACTION = 0.45
# Two different level sets this close in x, both price-plausible, are ambiguous.
AMBIGUITY_X_GAP = 80
# A CDX LONG/SHORT marker associates with a level cluster inside this box.
MARKER_X_DISTANCE = 220
MARKER_Y_PAD = 80

_LEVEL_LABELS = {"ENTRY", "SL", "TP1", "TP2"}
NAVIGATION_REASONS = {
    Reason.VISION_NO_CDX_TEXT.value,
    Reason.VISION_NO_CURRENT_CDX_LEVELS.value,
    Reason.VISION_LEVELS_NOT_VISIBLE.value,
    Reason.VISION_CURRENT_SIGNAL_OFFSCREEN.value,
    Reason.VISION_REJECT_STALE_TRADE_LEVELS.value,
}


@dataclass(frozen=True)
class CandidateVerdict:
    candidate: CDXLevelCandidate
    cluster_x: float
    x_fraction: float
    status: str


def should_navigate(reasons: list[str]) -> bool:
    return any(reason in NAVIGATION_REASONS for reason in reasons)


def select_active(
    candidates: list[CDXLevelCandidate],
    tokens: list[OCRToken],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    sanity_points: Decimal,
) -> tuple[CDXLevelCandidate | None, list[str], list[CandidateVerdict]]:
    verdicts = classify(candidates, tokens, webhook_direction=webhook_direction, webhook_price=webhook_price, sanity_points=sanity_points)
    current = [item for item in verdicts if item.status == "CURRENT"]
    if not current:
        directional = [item for item in verdicts if item.status == "DIRECTION_CONFLICT"]
        stale = [item for item in verdicts if item.status == "STALE"]
        if directional:
            return None, [Reason.VISION_DIRECTION_CONFLICT.value], verdicts
        if stale:
            return None, [Reason.VISION_CURRENT_SIGNAL_OFFSCREEN.value, Reason.VISION_REJECT_STALE_TRADE_LEVELS.value], verdicts
        return None, [Reason.VISION_NO_CURRENT_CDX_LEVELS.value], verdicts
    current.sort(key=lambda item: item.cluster_x, reverse=True)
    best = current[0]
    if len(current) > 1:
        second = current[1]
        same_levels = (best.candidate.stop, best.candidate.tp1, best.candidate.tp2) == (
            second.candidate.stop,
            second.candidate.tp1,
            second.candidate.tp2,
        )
        if not same_levels and abs(best.cluster_x - second.cluster_x) < AMBIGUITY_X_GAP:
            return None, [Reason.VISION_AMBIGUOUS_LEVEL_SET.value], verdicts
    return best.candidate, [], verdicts


def classify(
    candidates: list[CDXLevelCandidate],
    tokens: list[OCRToken],
    *,
    webhook_direction: str,
    webhook_price: Decimal | None,
    sanity_points: Decimal,
) -> list[CandidateVerdict]:
    width = pane_width(tokens, candidates)
    markers = [(normalize_label(token.text), token) for token in tokens if normalize_label(token.text) in {"LONG", "SHORT"}]
    centers = [cluster_x(candidate) for candidate in candidates]
    verdicts: list[CandidateVerdict] = []
    for candidate, center in zip(candidates, centers):
        fraction = center / width if width else 0.0
        newer_on_the_right = any(other > center + AMBIGUITY_X_GAP for other in centers)
        if newer_on_the_right and fraction < STALE_X_FRACTION:
            status = "STALE"
        elif _direction_conflict(candidate, markers, webhook_direction):
            status = "DIRECTION_CONFLICT"
        elif not _price_plausible(candidate, webhook_price, sanity_points):
            status = "PRICE_FAR"
        else:
            status = "CURRENT"
        verdicts.append(CandidateVerdict(candidate, center, fraction, status))
    return verdicts


def cluster_x(candidate: CDXLevelCandidate) -> float:
    xs = [((level.x1 + level.x2) / 2) for level in candidate.levels if level.normalized_label in _LEVEL_LABELS]
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def pane_width(tokens: list[OCRToken], candidates: list[CDXLevelCandidate]) -> float:
    edges = [token.x2 for token in tokens]
    edges.extend(level.x2 for candidate in candidates for level in candidate.levels)
    return float(max(edges)) if edges else 1.0


def _direction_conflict(candidate: CDXLevelCandidate, markers: list[tuple[str, OCRToken]], webhook_direction: str) -> bool:
    ys = [level.y1 for level in candidate.levels] + [level.y2 for level in candidate.levels]
    if not ys:
        return False
    top, bottom = min(ys) - MARKER_Y_PAD, max(ys) + MARKER_Y_PAD
    center = cluster_x(candidate)
    for label, token in markers:
        if not (top <= token.cy <= bottom):
            continue
        if abs(token.cx - center) > MARKER_X_DISTANCE:
            continue
        if label != webhook_direction:
            return True
    return False


def _price_plausible(candidate: CDXLevelCandidate, webhook_price: Decimal | None, sanity_points: Decimal) -> bool:
    if webhook_price is None:
        return True
    reference = candidate.visual_entry if candidate.visual_entry is not None else None
    if reference is None and candidate.entry_source == "VISION":
        reference = candidate.entry
    if reference is not None and candidate.entry_source == "VISION":
        return abs(reference - webhook_price) <= sanity_points
    return any(abs(price - webhook_price) <= sanity_points for price in (candidate.stop, candidate.tp1, candidate.tp2))
