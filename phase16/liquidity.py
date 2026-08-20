"""Frozen Phase 4 BSL/SSL liquidity engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List

from .config import FrozenConfig
from .models import LiquidityEvent


@dataclass
class LiquidityLevel:
    price: float
    origin_bar: int
    confirmation_bar: int
    is_buy_side: bool
    is_equal: bool


@dataclass
class LiquidityEngine:
    config: FrozenConfig
    buy_side: List[LiquidityLevel] = field(default_factory=list)
    sell_side: List[LiquidityLevel] = field(default_factory=list)
    previous_swing_high: float = float("nan")
    previous_swing_low: float = float("nan")

    def _is_duplicate(self, levels: List[LiquidityLevel], price: float) -> bool:
        return any(abs(level.price - price) < self.config.minimum_tick for level in levels)

    def step(
        self,
        *,
        bar_index: int,
        high: float,
        low: float,
        close: float,
        pivot_high: float = float("nan"),
        pivot_low: float = float("nan"),
    ) -> LiquidityEvent:
        """Check existing levels before adding newly confirmed pivots."""
        event = LiquidityEvent()
        for index in range(len(self.buy_side) - 1, -1, -1):
            level = self.buy_side[index]
            if bar_index <= level.confirmation_bar:
                continue
            # Pine checks rejection/sweep before close-through consumption.
            if high > level.price and close < level.price:
                event.bsl_sweep = True
                self.buy_side.pop(index)
            elif close > level.price:
                event.bsl_consumed = True
                self.buy_side.pop(index)

        for index in range(len(self.sell_side) - 1, -1, -1):
            level = self.sell_side[index]
            if bar_index <= level.confirmation_bar:
                continue
            if low < level.price and close > level.price:
                event.ssl_sweep = True
                self.sell_side.pop(index)
            elif close < level.price:
                event.ssl_consumed = True
                self.sell_side.pop(index)

        tolerance = self.config.liquidity_equal_ticks * self.config.minimum_tick
        if math.isfinite(float(pivot_high)):
            price = float(pivot_high)
            if not self._is_duplicate(self.buy_side, price):
                equal = math.isfinite(self.previous_swing_high) and (
                    abs(price - self.previous_swing_high) <= tolerance
                )
                self.buy_side.append(
                    LiquidityLevel(
                        price,
                        bar_index - self.config.liquidity_right,
                        bar_index,
                        True,
                        equal,
                    )
                )
                if len(self.buy_side) > self.config.liquidity_max_levels:
                    self.buy_side.pop(0)
            self.previous_swing_high = price

        if math.isfinite(float(pivot_low)):
            price = float(pivot_low)
            if not self._is_duplicate(self.sell_side, price):
                equal = math.isfinite(self.previous_swing_low) and (
                    abs(price - self.previous_swing_low) <= tolerance
                )
                self.sell_side.append(
                    LiquidityLevel(
                        price,
                        bar_index - self.config.liquidity_right,
                        bar_index,
                        False,
                        equal,
                    )
                )
                if len(self.sell_side) > self.config.liquidity_max_levels:
                    self.sell_side.pop(0)
            self.previous_swing_low = price
        return event

