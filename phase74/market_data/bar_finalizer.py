"""Bar finalization semantics for 1-minute NQ bars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class BarLifecycle:
    bar_start: datetime
    bar_end: datetime
    bar_received_at: datetime
    bar_finalized_at: datetime
    data_latency_ms: float

    @staticmethod
    def from_bar_open(bar_start: datetime, *, received_at: datetime | None = None, finalized_at: datetime | None = None) -> "BarLifecycle":
        if bar_start.tzinfo is None:
            bar_start = bar_start.replace(tzinfo=timezone.utc)
        bar_end = bar_start + timedelta(minutes=1)
        recv = received_at or datetime.now(timezone.utc)
        fin = finalized_at or recv
        latency_ms = (fin - bar_end).total_seconds() * 1000.0
        return BarLifecycle(
            bar_start=bar_start,
            bar_end=bar_end,
            bar_received_at=recv,
            bar_finalized_at=fin,
            data_latency_ms=latency_ms,
        )

    def is_closed_at(self, now: datetime) -> bool:
        return now >= self.bar_end

    def to_dict(self) -> dict:
        return {
            "bar_start": self.bar_start.isoformat(),
            "bar_end": self.bar_end.isoformat(),
            "bar_received_at": self.bar_received_at.isoformat(),
            "bar_finalized_at": self.bar_finalized_at.isoformat(),
            "data_latency_ms": self.data_latency_ms,
        }
