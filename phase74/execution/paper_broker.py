"""Paper broker adapter — LOCAL_SIM when no external paper venue available."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from phase73.execution.base import OrderRouter
from phase73.execution.orders import Fill, Order, OrderSide, OrderState
from phase73.execution.positions import PositionSnapshot
from phase73.execution.sim_router import SimOrderRouter
from phase74.contracts.mapping import ContractSpec, validate_contract_for_order


class BrokerHealth(str, Enum):
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    EXECUTION_MODE_UNVERIFIED = "EXECUTION_MODE_UNVERIFIED"


@dataclass
class PaperBrokerAdapter(OrderRouter):
    """
    Paper execution adapter wrapping SimOrderRouter.
    No Tradovate/Rithmic credentials required — LOCAL_SIM dress rehearsal.
    """

    paper_mode: bool
    contract: ContractSpec
    protective_orders: str = "CLIENT_SIDE_PROTECTION"
    inner: SimOrderRouter = field(default_factory=SimOrderRouter)
    broker_position: PositionSnapshot = field(default_factory=PositionSnapshot)
    open_orders: list[Order] = field(default_factory=list)
    connected: bool = False
    last_fill: Fill | None = None
    last_slippage: dict[str, float] = field(default_factory=dict)

    def connect(self) -> BrokerHealth:
        if not self.paper_mode:
            self.connected = False
            return BrokerHealth.EXECUTION_MODE_UNVERIFIED
        self.connected = True
        return BrokerHealth.CONNECTED

    def disconnect(self) -> None:
        self.connected = False

    def health(self) -> BrokerHealth:
        if not self.paper_mode:
            return BrokerHealth.EXECUTION_MODE_UNVERIFIED
        return BrokerHealth.CONNECTED if self.connected else BrokerHealth.DISCONNECTED

    def get_position(self) -> PositionSnapshot:
        return self.broker_position

    def get_open_orders(self) -> list[Order]:
        return list(self.open_orders)

    def _verify_ready(self, order: Order) -> tuple[Order, Fill | None]:
        if not self.paper_mode:
            order.state = OrderState.REJECTED
            order.reject_reason = "EXECUTION_MODE_UNVERIFIED"
            return order, None
        if not self.connected:
            order.state = OrderState.REJECTED
            order.reject_reason = "BROKER_DISCONNECTED"
            return order, None
        err = validate_contract_for_order(self.contract)
        if err:
            order.state = OrderState.REJECTED
            order.reject_reason = err
            return order, None
        return order, None  # type: ignore

    def submit(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        chk, fill = self._verify_ready(order)
        if fill is None and order.state == OrderState.REJECTED:
            return chk, None
        if chk.state == OrderState.REJECTED:
            return chk, None

        px = self.contract.resolve_broker_price(market_price)
        order, fill = self.inner.submit(order, px)
        if fill:
            self.last_fill = fill
            side = "LONG" if order.side == OrderSide.BUY else "SHORT"
            self.broker_position = PositionSnapshot(side=side, quantity=order.quantity, entry_price=fill.price, entry_time=fill.filled_at)
            self.open_orders = [o for o in self.open_orders if o.order_id != order.order_id]
        else:
            self.open_orders.append(order)
        return order, fill

    def flatten(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        order, fill = self.submit(order, market_price)
        if fill:
            self.broker_position = PositionSnapshot()
        return order, fill

    def cancel_order(self, order_id: str) -> bool:
        self.open_orders = [o for o in self.open_orders if o.order_id != order_id]
        return True

    def close_and_reverse(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        return self.submit(order, market_price)

    def record_slippage(self, signal_price: float, fill_price: float, risk: float) -> dict[str, float]:
        ticks = self.contract.slippage_ticks(signal_price, fill_price)
        pts = fill_price - signal_price
        slippage_r = pts / risk if risk else 0.0
        self.last_slippage = {"slippage_points": pts, "slippage_ticks": ticks, "slippage_R": slippage_r}
        return self.last_slippage
