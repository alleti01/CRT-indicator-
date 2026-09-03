"""Provider-independent market data interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Sequence

from phase73.market_data.bar import Bar
from phase73.market_data.health import HealthReport


class MarketDataProvider(ABC):
    @abstractmethod
    def current_time(self) -> datetime:
        ...

    @abstractmethod
    def latest_bar(self) -> Bar | None:
        ...

    @abstractmethod
    def recent_bars(self, n: int) -> Sequence[Bar]:
        ...

    @abstractmethod
    def health(self) -> HealthReport:
        ...

    @abstractmethod
    def advance(self) -> bool:
        """Advance one bar in replay mode; no-op/live returns False when no new bar."""
        ...

    @abstractmethod
    def atr(self, period: int = 14) -> float:
        ...

    def snapshot_features(self, signal_price: float | None = None, signal_time: datetime | None = None) -> dict:
        bars = list(self.recent_bars(15))
        atr = self.atr()
        last = bars[-1] if bars else None
        now = self.current_time()
        out: dict = {
            "current_price": last.close if last else None,
            "current_atr": atr,
            "last_3_bars": bars[-3:],
            "last_5_bars": bars[-5:],
            "last_10_bars": bars[-10:],
            "last_15_bars": bars[-15:],
            "rolling_high_10": max(b.high for b in bars[-10:]) if len(bars) >= 1 else None,
            "rolling_low_10": min(b.low for b in bars[-10:]) if len(bars) >= 1 else None,
            "health": self.health(),
        }
        if signal_price is not None and last is not None:
            dist = last.close - signal_price
            out["distance_from_signal"] = dist
            out["distance_from_signal_atr"] = dist / atr if atr > 0 else 0.0
        if signal_time is not None:
            out["time_since_signal_seconds"] = (now - signal_time).total_seconds()
        return out
