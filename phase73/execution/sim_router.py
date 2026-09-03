"""Simulated immediate-fill order router."""
from __future__ import annotations

from phase73.execution.base import OrderRouter
from phase73.execution.orders import Fill, Order, OrderSide, OrderState


class SimOrderRouter(OrderRouter):
    def __init__(self, reject_next: bool = False) -> None:
        self._open_orders: dict[str, Order] = {}
        self._reject_next = reject_next
        self.submitted: list[Order] = []

    def submit(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        if self._reject_next:
            self._reject_next = False
            order.state = OrderState.REJECTED
            order.reject_reason = "SIM_REJECT"
            return order, None

        if order.order_id in self._open_orders:
            order.state = OrderState.REJECTED
            order.reject_reason = "DUPLICATE_ORDER"
            return order, None

        order.state = OrderState.SUBMITTED
        order.submitted_at = order.created_at
        order.state = OrderState.ACKNOWLEDGED
        order.state = OrderState.FILLED
        order.filled_at = order.created_at
        fill = Fill.from_order(order, market_price)
        self._open_orders[order.order_id] = order
        self.submitted.append(order)
        return order, fill

    def flatten(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        return self.submit(order, market_price)

    def arm_reject_next(self) -> None:
        self._reject_next = True
