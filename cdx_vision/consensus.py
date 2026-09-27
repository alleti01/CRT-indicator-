"""Two consecutive identical reads confirm a level set. A 2-1 vote does not."""
from __future__ import annotations

from cdx_vision.models import CDXLevelCandidate, Reason


def _key(candidate: CDXLevelCandidate) -> tuple:
    return (candidate.stop, candidate.tp1, candidate.tp2, candidate.entry)


def consensus(frames: list[CDXLevelCandidate | None]) -> tuple[CDXLevelCandidate | None, list[str], bool]:
    """Return candidate, reasons, ocr_unstable.

    Confirmation requires two consecutive frames with the same SL, TP1, TP2, and entry.
    A majority that is not consecutive is logged as unstable and rejected.
    """
    present = [frame for frame in frames if frame is not None]
    if len(present) < 2:
        return None, [Reason.VISION_NO_CONSENSUS.value], False
    for left, right in zip(present, present[1:]):
        if _key(left) == _key(right):
            return left, [Reason.VISION_CONFIRMED.value], False
    counts: dict[tuple, int] = {}
    for frame in present:
        counts[_key(frame)] = counts.get(_key(frame), 0) + 1
    unstable = max(counts.values()) >= 2
    return None, [Reason.VISION_NO_CONSENSUS.value], unstable
