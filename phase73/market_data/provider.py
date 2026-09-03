"""Replay and live provider implementations."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Iterator, Sequence

import pandas as pd

from phase73.market_data.bar import Bar
from phase73.market_data.base import MarketDataProvider
from phase73.market_data.cache import BarCache
from phase73.market_data.health import DataHealth, HealthReport


def _row_to_bar(ts: pd.Timestamp, row) -> Bar:
    t = ts.to_pydatetime()
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    else:
        t = t.astimezone(timezone.utc)
    return Bar(
        timestamp=t,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row.get("volume", 0.0)),
    )


class ReplayDataProvider(MarketDataProvider):
    """Sequential replay from local 1m dataframe."""

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        start_index: int = 0,
        staleness_limit_seconds: int = 90,
        atr_period: int = 14,
    ) -> None:
        self._df = df
        self._i = start_index
        self._cache = BarCache()
        self._staleness_limit = staleness_limit_seconds
        self._atr_period = atr_period
        self._sim_now: datetime | None = None
        # warm cache up to start_index
        for j in range(0, min(start_index + 1, len(df))):
            self._ingest_row(j)

    def _ingest_row(self, idx: int) -> Bar:
        ts = self._df.index[idx]
        bar = _row_to_bar(ts, self._df.iloc[idx])
        self._cache.append(bar)
        self._sim_now = bar.timestamp
        return bar

    def current_time(self) -> datetime:
        if self._sim_now is not None:
            return self._sim_now
        return datetime.now(timezone.utc)

    def latest_bar(self) -> Bar | None:
        return self._cache.latest()

    def recent_bars(self, n: int) -> Sequence[Bar]:
        return self._cache.recent(n)

    def health(self) -> HealthReport:
        last = self._cache.latest()
        now = self.current_time()
        if last is None:
            return HealthReport(DataHealth.DATA_MISSING, current_time=now, detail="no bars")
        latency = (now - last.timestamp).total_seconds()
        if self._cache.out_of_order_bars > 0:
            return HealthReport(
                DataHealth.DATA_OUT_OF_ORDER,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                latency_seconds=latency,
                out_of_order_bars=self._cache.out_of_order_bars,
            )
        if self._cache.gap_bars > 0:
            return HealthReport(
                DataHealth.DATA_GAP,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                latency_seconds=latency,
                missing_bars=self._cache.gap_bars,
            )
        if latency > self._staleness_limit:
            return HealthReport(
                DataHealth.DATA_STALE,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                latency_seconds=latency,
            )
        return HealthReport(
            DataHealth.DATA_HEALTHY,
            last_bar_timestamp=last.timestamp,
            current_time=now,
            latency_seconds=latency,
            duplicate_bars=self._cache.duplicate_bars,
        )

    def advance(self) -> bool:
        next_i = self._i + 1
        if next_i >= len(self._df):
            return False
        self._i = next_i
        self._ingest_row(next_i)
        return True

    def atr(self, period: int = 14) -> float:
        return self._cache.atr(period or self._atr_period)

    @property
    def index(self) -> int:
        return self._i

    def iter_bars(self) -> Iterator[Bar]:
        while True:
            bar = self.latest_bar()
            if bar is not None:
                yield bar
            if not self.advance():
                break


class LiveDataProvider(MarketDataProvider):
    """Stub for future live feed — not connected in Phase73."""

    def __init__(self) -> None:
        raise NotImplementedError("LIVE_DATA_PROVIDER not available in Phase73")

    def current_time(self) -> datetime:
        raise NotImplementedError

    def latest_bar(self) -> Bar | None:
        raise NotImplementedError

    def recent_bars(self, n: int) -> Sequence[Bar]:
        raise NotImplementedError

    def health(self) -> HealthReport:
        raise NotImplementedError

    def advance(self) -> bool:
        raise NotImplementedError

    def atr(self, period: int = 14) -> float:
        raise NotImplementedError
