"""Sim router with adverse slippage for conservative paper fills."""
from __future__ import annotations

from phase73.execution.orders import Order, OrderSide
from phase73.execution.sim_router import SimOrderRouter


class SlippageSimRouter(SimOrderRouter):
    def __init__(
        self,
        *,
        entry_slippage_ticks: float = 1.0,
        exit_slippage_ticks: float = 1.0,
        tick_size: float = 0.25,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.entry_slippage_ticks = entry_slippage_ticks
        self.exit_slippage_ticks = exit_slippage_ticks
        self.tick_size = tick_size

    def _adverse_price(self, order: Order, market_price: float) -> float:
        ticks = self.exit_slippage_ticks if order.action == "FLATTEN" else self.entry_slippage_ticks
        slip = ticks * self.tick_size
        if order.side == OrderSide.BUY:
            return market_price + slip
        return market_price - slip

    def submit(self, order: Order, market_price: float) -> tuple[Order, object]:
        return super().submit(order, self._adverse_price(order, market_price))
