"""Position tracking."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


PositionSide = Literal["FLAT", "LONG", "SHORT"]


class PositionSource(str, Enum):
    INTERNAL = "INTERNAL"
    BROKER = "BROKER"
    DESIRED = "DESIRED"


@dataclass
class PositionSnapshot:
    side: PositionSide = "FLAT"
    quantity: int = 0
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    entry_time: datetime | None = None
    signal_id: str = ""
    mfe_r: float = 0.0
    mae_r: float = 0.0
    current_r: float = 0.0
    bars_in_trade: int = 0
    minutes_in_trade: float = 0.0


@dataclass
class PositionBook:
    desired: PositionSnapshot = field(default_factory=PositionSnapshot)
    internal: PositionSnapshot = field(default_factory=PositionSnapshot)
    broker: PositionSnapshot = field(default_factory=PositionSnapshot)

    def mismatch(self) -> bool:
        sides = {self.desired.side, self.internal.side, self.broker.side}
        # allow desired ahead of broker briefly only if internal matches desired
        if self.internal.side != self.broker.side:
            return True
        if self.internal.quantity != self.broker.quantity and self.internal.side != "FLAT":
            return True
        return False
