"""Prop day halt for a $2,000 DD / 50k / 1 NQ book (America/New_York session)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

_NY = ZoneInfo("America/New_York")
NQ_POINT_VALUE = 20.0


def session_date_ny(now: datetime | None = None) -> date:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(_NY).date()


def nq_dollars(net_r: float, atr_points: float, point_value: float = NQ_POINT_VALUE) -> float:
    return float(net_r) * float(atr_points) * float(point_value)


@dataclass
class PropDayHalt:
    max_losers: int = 2
    max_loss_dollars: float = 400.0
    max_winners: int = 2
    big_win_dollars: float = 500.0
    giveback_arm_dollars: float = 400.0
    giveback_dollars: float = 300.0
    point_value: float = NQ_POINT_VALUE
    realized_r: float = 0.0
    realized_dollars: float = 0.0
    losers: int = 0
    winners: int = 0
    peak_dollars: float = 0.0
    had_big_win: bool = False
    session_date: date = field(default_factory=session_date_ny)
    reason: str = ""

    def _roll(self, now: datetime | None = None) -> None:
        today = session_date_ny(now)
        if today != self.session_date:
            self.session_date = today
            self.realized_r = 0.0
            self.realized_dollars = 0.0
            self.losers = 0
            self.winners = 0
            self.peak_dollars = 0.0
            self.had_big_win = False
            self.reason = ""

    def record_closed(
        self,
        net_r: float,
        now: datetime | None = None,
        *,
        dollars: float | None = None,
        atr: float | None = None,
    ) -> None:
        self._roll(now)
        if dollars is None and atr is not None:
            dollars = nq_dollars(net_r, atr, self.point_value)
        if dollars is None:
            dollars = 0.0
        self.realized_r += net_r
        self.realized_dollars += dollars
        self.peak_dollars = max(self.peak_dollars, self.realized_dollars)
        if dollars >= self.big_win_dollars:
            self.had_big_win = True
        if dollars < 0 or net_r < 0:
            self.losers += 1
        elif dollars > 0 or net_r > 0:
            self.winners += 1

    def should_halt_new_entries(self, now: datetime | None = None) -> bool:
        self._roll(now)
        if self.losers >= self.max_losers:
            self.reason = "HALT_DAY_LOSERS"
            return True
        if self.realized_dollars <= -abs(self.max_loss_dollars):
            self.reason = "HALT_DAY_DOLLARS"
            return True
        if self.had_big_win:
            self.reason = "HALT_DAY_BIG_WIN"
            return True
        if self.winners >= self.max_winners:
            self.reason = "HALT_DAY_WINS"
            return True
        if (
            self.peak_dollars >= self.giveback_arm_dollars
            and self.realized_dollars <= self.peak_dollars - self.giveback_dollars
        ):
            self.reason = "HALT_DAY_GIVEBACK"
            return True
        self.reason = ""
        return False
