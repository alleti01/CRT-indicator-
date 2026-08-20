"""Independent one-active-trade-per-model Phase 14 simulator."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .config import FrozenConfig
from .models import MODELS, EntryEvent, Trade


@dataclass
class TradeEngine:
    config: FrozenConfig
    active: Dict[str, Trade] = field(default_factory=dict)
    completed: List[Trade] = field(default_factory=list)
    attempts: Dict[str, int] = field(default_factory=lambda: {model: 0 for model in MODELS})
    accepted: Dict[str, int] = field(default_factory=lambda: {model: 0 for model in MODELS})

    def try_open(
        self,
        event: EntryEvent,
        *,
        bar_index: int,
        close: float,
        atr: float,
    ) -> bool:
        self.attempts[event.model] += 1
        if event.model in self.active:
            return False
        resolved_atr = float(atr) if math.isfinite(float(atr)) else 1.0
        risk = self.config.trade_stop_atr * resolved_atr
        stop = close - risk if event.direction == 1 else close + risk
        target = (
            close + risk * self.config.trade_target_r
            if event.direction == 1
            else close - risk * self.config.trade_target_r
        )
        self.active[event.model] = Trade(
            model=event.model,
            direction=event.direction,
            setup_timestamp=event.setup_timestamp,
            bos_timestamp=event.bos_timestamp,
            retest_timestamp=event.retest_timestamp,
            confirm_timestamp=event.confirm_timestamp,
            entry_timestamp=event.entry_timestamp,
            entry_bar=bar_index,
            entry_price=float(close),
            stop_price=float(stop),
            target_price=float(target),
            risk=float(risk),
            score=float(event.score),
            htf_regime=int(event.htf_regime),
            session_bucket=int(event.session_bucket),
        )
        self.accepted[event.model] += 1
        return True

    def _close(
        self,
        model: str,
        *,
        timestamp: pd.Timestamp,
        exit_price: float,
        result_r: float,
        reason: str,
    ) -> None:
        trade = self.active.pop(model)
        trade.exit_timestamp = timestamp
        trade.exit_price = float(exit_price)
        trade.result_R = float(result_r)
        trade.exit_reason = reason
        self.completed.append(trade)

    def manage_bar(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        bar_end: pd.Timestamp,
        high: float,
        low: float,
        close: float,
        end_exclusive: pd.Timestamp,
        previous_close: Optional[float] = None,
        previous_timestamp: Optional[pd.Timestamp] = None,
    ) -> None:
        """Manage existing positions after all same-bar entry attempts."""
        for model in MODELS:
            if model not in self.active:
                continue
            trade = self.active[model]
            elapsed = bar_index - trade.entry_bar
            if timestamp >= end_exclusive:
                price = float(previous_close if previous_close is not None else close)
                exit_ts = previous_timestamp if previous_timestamp is not None else timestamp
                result = (
                    (price - trade.entry_price) / trade.risk
                    if trade.direction == 1 and trade.risk > 0
                    else (trade.entry_price - price) / trade.risk
                    if trade.risk > 0
                    else 0.0
                )
                self._close(
                    model,
                    timestamp=exit_ts,
                    exit_price=price,
                    result_r=result,
                    reason="WINDOW_END",
                )
                continue
            if elapsed < 1:
                continue

            result: Optional[float] = None
            price: Optional[float] = None
            reason: Optional[str] = None
            if trade.direction == 1:
                if low <= trade.stop_price:  # STOP first on ambiguous bars.
                    result, price, reason = -1.0, trade.stop_price, "STOP"
                elif high >= trade.target_price:
                    result, price, reason = (
                        self.config.trade_target_r,
                        trade.target_price,
                        "TARGET",
                    )
                elif elapsed >= self.config.trade_max_bars:
                    result = (close - trade.entry_price) / trade.risk if trade.risk > 0 else 0.0
                    price, reason = close, "TIME"
                elif bar_end >= end_exclusive:
                    result = (close - trade.entry_price) / trade.risk if trade.risk > 0 else 0.0
                    price, reason = close, "WINDOW_END"
            else:
                if high >= trade.stop_price:
                    result, price, reason = -1.0, trade.stop_price, "STOP"
                elif low <= trade.target_price:
                    result, price, reason = (
                        self.config.trade_target_r,
                        trade.target_price,
                        "TARGET",
                    )
                elif elapsed >= self.config.trade_max_bars:
                    result = (trade.entry_price - close) / trade.risk if trade.risk > 0 else 0.0
                    price, reason = close, "TIME"
                elif bar_end >= end_exclusive:
                    result = (trade.entry_price - close) / trade.risk if trade.risk > 0 else 0.0
                    price, reason = close, "WINDOW_END"
            if result is not None and price is not None and reason is not None:
                self._close(
                    model,
                    timestamp=timestamp,
                    exit_price=price,
                    result_r=result,
                    reason=reason,
                )

    def close_remaining(
        self, *, timestamp: pd.Timestamp, close: float, reason: str = "DATA_END"
    ) -> None:
        """Deterministically mark positions when data ends before the window boundary."""
        for model in list(self.active):
            trade = self.active[model]
            result = (
                (close - trade.entry_price) / trade.risk
                if trade.direction == 1 and trade.risk > 0
                else (trade.entry_price - close) / trade.risk
                if trade.risk > 0
                else 0.0
            )
            self._close(
                model,
                timestamp=timestamp,
                exit_price=close,
                result_r=result,
                reason=reason,
            )

