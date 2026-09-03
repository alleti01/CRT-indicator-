"""Market data health states."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DataHealth(str, Enum):
    DATA_HEALTHY = "DATA_HEALTHY"
    DATA_STALE = "DATA_STALE"
    DATA_MISSING = "DATA_MISSING"
    DATA_GAP = "DATA_GAP"
    DATA_OUT_OF_ORDER = "DATA_OUT_OF_ORDER"


@dataclass
class HealthReport:
    state: DataHealth
    last_bar_timestamp: datetime | None = None
    current_time: datetime | None = None
    latency_seconds: float = 0.0
    missing_bars: int = 0
    duplicate_bars: int = 0
    out_of_order_bars: int = 0
    detail: str = ""
