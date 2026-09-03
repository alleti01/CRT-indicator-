"""Order and fill models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal
import uuid


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"


class OrderState(str, Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELED = "CANCELED"


OrderAction = Literal["MARKET_BUY", "MARKET_SELL", "FLATTEN", "CLOSE_AND_REVERSE"]


@dataclass
class Order:
    order_id: str
    action: OrderAction
    side: OrderSide
    quantity: int
    symbol: str
    state: OrderState = OrderState.CREATED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    reject_reason: str = ""
    signal_id: str = ""

    @staticmethod
    def new(action: OrderAction, side: OrderSide, quantity: int, symbol: str, signal_id: str = "") -> "Order":
        return Order(
            order_id=str(uuid.uuid4()),
            action=action,
            side=side,
            quantity=quantity,
            symbol=symbol,
            signal_id=signal_id,
        )


@dataclass
class Fill:
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    filled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @staticmethod
    def from_order(order: Order, price: float) -> "Fill":
        return Fill(
            fill_id=str(uuid.uuid4()),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            filled_at=datetime.now(timezone.utc),
        )
