"""Rolling bar cache + ATR."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Deque

from phase73.market_data.bar import Bar


class BarCache:
    def __init__(self, maxlen: int = 500) -> None:
        self._bars: Deque[Bar] = deque(maxlen=maxlen)
        self._last_ts: datetime | None = None
        self.duplicate_bars = 0
        self.out_of_order_bars = 0
        self.gap_bars = 0

    def append(self, bar: Bar, *, expected_minutes: int = 1) -> None:
        if self._last_ts is not None:
            if bar.timestamp == self._last_ts:
                self.duplicate_bars += 1
                return
            if bar.timestamp < self._last_ts:
                self.out_of_order_bars += 1
                return
            delta = (bar.timestamp - self._last_ts).total_seconds() / 60.0
            if delta > expected_minutes:
                self.gap_bars += int(delta - expected_minutes)
        self._bars.append(bar)
        self._last_ts = bar.timestamp

    def recent(self, n: int) -> list[Bar]:
        if n >= len(self._bars):
            return list(self._bars)
        return list(self._bars)[-n:]

    def latest(self) -> Bar | None:
        return self._bars[-1] if self._bars else None

    def atr(self, period: int = 14) -> float:
        bars = list(self._bars)
        if len(bars) < period + 1:
            return 0.0
        trs: list[float] = []
        for i in range(-period, 0):
            cur = bars[i]
            prev = bars[i - 1]
            tr = max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
            trs.append(tr)
        return sum(trs) / len(trs)

    def clear(self) -> None:
        self._bars.clear()
        self._last_ts = None
