"""Typed vision records. Prices are Decimal after parsing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class VisionState(str, Enum):
    IDLE = "IDLE"
    CAPTURE_REQUESTED = "CAPTURE_REQUESTED"
    WINDOW_VALIDATION = "WINDOW_VALIDATION"
    CAPTURING = "CAPTURING"
    PARSING = "PARSING"
    VALIDATING = "VALIDATING"
    CONSENSUS_PENDING = "CONSENSUS_PENDING"
    VISION_CONFIRMED = "VISION_CONFIRMED"
    VISION_REJECTED = "VISION_REJECTED"
    VISION_TIMEOUT = "VISION_TIMEOUT"


class Reason(str, Enum):
    VISION_CONFIRMED = "VISION_CONFIRMED"
    VISION_DISABLED = "VISION_DISABLED"
    VISION_WINDOW_NOT_FOUND = "VISION_WINDOW_NOT_FOUND"
    VISION_TRADINGVIEW_NOT_VISIBLE = "VISION_TRADINGVIEW_NOT_VISIBLE"
    VISION_TIMEOUT = "VISION_TIMEOUT"
    VISION_NO_CDX_TEXT = "VISION_NO_CDX_TEXT"
    VISION_ENTRY_NOT_FOUND = "VISION_ENTRY_NOT_FOUND"
    VISION_SL_NOT_FOUND = "VISION_SL_NOT_FOUND"
    VISION_TP1_NOT_FOUND = "VISION_TP1_NOT_FOUND"
    VISION_TP2_NOT_FOUND = "VISION_TP2_NOT_FOUND"
    VISION_OFF_TICK = "VISION_OFF_TICK"
    VISION_DIRECTION_CONFLICT = "VISION_DIRECTION_CONFLICT"
    VISION_INVALID_ORDERING = "VISION_INVALID_ORDERING"
    VISION_NO_CONSENSUS = "VISION_NO_CONSENSUS"
    VISION_OCR_UNSTABLE = "VISION_OCR_UNSTABLE"
    VISION_AMBIGUOUS_LEVEL_SET = "VISION_AMBIGUOUS_LEVEL_SET"
    VISION_SANITY_FAIL = "VISION_SANITY_FAIL"
    VISION_REJECT_RESTART_STALE = "VISION_REJECT_RESTART_STALE"
    VISION_DUPLICATE = "VISION_DUPLICATE"
    VISION_WINDOW_MINIMIZED = "VISION_WINDOW_MINIMIZED"
    VISION_CAPTURE_INVALID = "VISION_CAPTURE_INVALID"


@dataclass(frozen=True)
class VisionCaptureRequest:
    signal_id: str
    direction: str
    ticker: str
    webhook_received_at: datetime
    webhook_price: Decimal | None = None


@dataclass(frozen=True)
class OCRToken:
    text: str
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


@dataclass(frozen=True)
class ParsedLevel:
    raw_text: str
    normalized_label: str
    price: Decimal
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class CDXLevelCandidate:
    direction_seen: str
    entry: Decimal | None
    entry_source: str
    stop: Decimal
    tp1: Decimal
    tp2: Decimal
    levels: tuple[ParsedLevel, ...]


@dataclass
class VisionResult:
    signal_id: str
    state: VisionState
    reasons: list[str] = field(default_factory=list)
    direction: str = ""
    entry: Decimal | None = None
    entry_source: str = ""
    stop: Decimal | None = None
    tp1: Decimal | None = None
    tp2: Decimal | None = None
    frame_count: int = 0
    agreeing_frame_count: int = 0
    ocr_unstable: bool = False
    webhook_received_at: datetime | None = None
    capture_started_at: datetime | None = None
    confirmed_at: datetime | None = None
    window_title: str = ""
    window_bounds: str = ""
    debug_paths: list[str] = field(default_factory=list)

    @property
    def confirmed(self) -> bool:
        return self.state is VisionState.VISION_CONFIRMED
