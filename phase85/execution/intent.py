"""Strategy-facing intent. TraderEngine does not see NinjaTrader types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ExecutionIntent:
    side: str
    quantity: int
    instrument: str
    command_id: str
    event_id: str
    signal_id: str
    expected_entry: float | None = None
    signal_atr: float = 0.0
    signal_time: datetime | None = None
    webhook_received: datetime | None = None
    decision_time: datetime | None = None
    account: str = ""
    phase73_decision: str = "PASS"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def command(self) -> str:
        if self.side.upper() == "LONG":
            return "ENTER_LONG"
        if self.side.upper() == "SHORT":
            return "ENTER_SHORT"
        raise ValueError(f"invalid side {self.side}")
