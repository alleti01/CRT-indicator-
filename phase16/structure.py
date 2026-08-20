"""Frozen Phase 3 market-structure state machine."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import FrozenConfig
from .models import StructureEvent


@dataclass
class StructureEngine:
    config: FrozenConfig
    previous_high: float = float("nan")
    previous_low: float = float("nan")
    active_high: float = float("nan")
    active_low: float = float("nan")
    active_high_bar: int = -1
    active_low_bar: int = -1
    active_high_used: bool = False
    active_low_used: bool = False
    bias: int = 0

    def step(
        self,
        *,
        bar_index: int,
        high: float,
        low: float,
        close: float,
        pivot_high: float = float("nan"),
        pivot_low: float = float("nan"),
    ) -> StructureEvent:
        """Process break detection first, then same-bar pivot confirmations."""
        prior_high = self.active_high
        prior_low = self.active_low
        bias_before = self.bias
        high_probe = close if self.config.structure_break_mode == "Close" else high
        low_probe = close if self.config.structure_break_mode == "Close" else low
        bull_break = (
            math.isfinite(self.active_high)
            and not self.active_high_used
            and high_probe > self.active_high
        )
        bear_break = (
            math.isfinite(self.active_low)
            and not self.active_low_used
            and low_probe < self.active_low
        )
        if bull_break and bear_break:
            bull_break = False
            bear_break = False

        bull_choch = False
        bear_choch = False
        if bull_break:
            bull_choch = self.bias == -1
            self.active_high_used = True
            if bull_choch or self.bias == 0:
                self.bias = 1
        if bear_break:
            bear_choch = self.bias == 1
            self.active_low_used = True
            if bear_choch or self.bias == 0:
                self.bias = -1

        if math.isfinite(float(pivot_high)):
            self.previous_high = float(pivot_high)
            self.active_high = float(pivot_high)
            self.active_high_bar = bar_index - self.config.structure_right
            self.active_high_used = False
        if math.isfinite(float(pivot_low)):
            self.previous_low = float(pivot_low)
            self.active_low = float(pivot_low)
            self.active_low_bar = bar_index - self.config.structure_right
            self.active_low_used = False

        return StructureEvent(
            bull_bos=bull_break,
            bear_bos=bear_break,
            bull_choch=bull_choch,
            bear_choch=bear_choch,
            previous_active_high=prior_high,
            previous_active_low=prior_low,
            active_high=self.active_high,
            active_low=self.active_low,
            bias_before=bias_before,
            bias_after=self.bias,
        )

