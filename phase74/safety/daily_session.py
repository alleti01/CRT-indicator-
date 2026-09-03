"""Daily session safety tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class DailySessionSafety:
    daily_loss_limit: float
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    consecutive_errors: int = 0
    halted: bool = False
    session_date: date = field(default_factory=date.today)

    @property
    def daily_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl

    @property
    def loss_remaining(self) -> float:
        return self.daily_loss_limit + self.daily_pnl

    def record_realized(self, r_multiple: float, risk_dollars: float) -> None:
        self.realized_pnl += r_multiple * risk_dollars

    def record_error(self) -> None:
        self.consecutive_errors += 1

    def should_halt(self, max_consecutive_errors: int) -> bool:
        if self.daily_pnl <= -abs(self.daily_loss_limit):
            self.halted = True
            return True
        if self.consecutive_errors >= max_consecutive_errors:
            self.halted = True
            return True
        return self.halted
