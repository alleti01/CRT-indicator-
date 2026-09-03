"""Abstract order router."""
from __future__ import annotations

from abc import ABC, abstractmethod

from phase73.execution.orders import Fill, Order


class OrderRouter(ABC):
    @abstractmethod
    def submit(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        ...

    @abstractmethod
    def flatten(self, order: Order, market_price: float) -> tuple[Order, Fill | None]:
        ...
