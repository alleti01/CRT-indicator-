"""Prop day halt: 3 losers or -2R realized (America/New_York session)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")


def session_date_ny(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_NY).date()


@dataclass
class PropDayHalt:
    max_losers: int = 3
    max_loss_r: float = 2.0
    realized_r: float = 0.0
    losers: int = 0
    session_date: date = field(default_factory=session_date_ny)
    reason: str = ""

    def _roll(self, now: datetime | None = None) -> None:
        today = session_date_ny(now)
        if today != self.session_date:
            self.session_date = today
            self.realized_r = 0.0
            self.losers = 0
            self.reason = ""

    def record_closed(self, net_r: float, now: datetime | None = None) -> None:
        self._roll(now)
        self.realized_r += net_r
        if net_r < 0:
            self.losers += 1

    def should_halt_new_entries(self, now: datetime | None = None) -> bool:
        self._roll(now)
        if self.losers >= self.max_losers:
            self.reason = "HALT_DAY_LOSERS"
            return True
        if self.realized_r <= -abs(self.max_loss_r):
            self.reason = "HALT_DAY_R"
            return True
        self.reason = ""
        return False
