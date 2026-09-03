"""Live market data provider — stream mode + optional Databento."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Iterator, Sequence

import pandas as pd

from phase73.market_data.bar import Bar
from phase73.market_data.base import MarketDataProvider
from phase73.market_data.cache import BarCache
from phase73.market_data.health import DataHealth, HealthReport
from phase73.market_data.provider import ReplayDataProvider, _row_to_bar
from phase74.market_data.bar_finalizer import BarLifecycle
from phase74.market_data.connection import ConnectionState


class StreamLiveDataProvider(MarketDataProvider):
    """
    Production live provider: ingests CLOSED 1m bars only.
    Simulated-stream mode replays a dataframe bar-by-bar for parity testing.
    """

    def __init__(
        self,
        df: pd.DataFrame | None = None,
        *,
        staleness_limit_seconds: int = 90,
        atr_period: int = 14,
        exchange: str = "GLBX",
    ) -> None:
        self._df = df if df is not None else pd.DataFrame()
        self._i = -1
        self._cache = BarCache()
        self._staleness_limit = staleness_limit_seconds
        self._atr_period = atr_period
        self._exchange = exchange
        self._connection = ConnectionState.DATA_DISCONNECTED
        self._pending_bar: Bar | None = None
        self._pending_lifecycle: BarLifecycle | None = None
        self._sim_now: datetime | None = None
        self._last_lifecycle: BarLifecycle | None = None
        if len(self._df) > 0:
            self._connection = ConnectionState.DATA_CONNECTED

    @property
    def connection_state(self) -> ConnectionState:
        return self._connection

    @property
    def last_lifecycle(self) -> BarLifecycle | None:
        return self._last_lifecycle

    def connect(self) -> None:
        was_disconnected = self._connection == ConnectionState.DATA_DISCONNECTED
        self._connection = ConnectionState.DATA_CONNECTED if was_disconnected else ConnectionState.DATA_RECONNECTED
        # Simulated-stream bootstrap: match ReplayDataProvider initial closed bar for parity/tests.
        if len(self._df) > 0 and self._cache.latest() is None and self._i < 0:
            bar_end_time = self._df.index[0] + pd.Timedelta(minutes=1)
            end_dt = bar_end_time.to_pydatetime().replace(tzinfo=timezone.utc)
            self._finalize_row(0, end_dt)
            self._i = 0
            self._sim_now = end_dt

    def disconnect(self) -> None:
        self._connection = ConnectionState.DATA_DISCONNECTED

    def ingest_tick(self, bar: Bar, *, finalized: bool = False, now: datetime | None = None) -> Bar | None:
        """Ingest bar; only append to cache when finalized (closed)."""
        now = now or datetime.now(timezone.utc)
        lifecycle = BarLifecycle.from_bar_open(bar.timestamp, received_at=now, finalized_at=now if finalized else now)
        if not finalized:
            self._pending_bar = bar
            self._pending_lifecycle = lifecycle
            return None
        self._cache.append(bar)
        self._sim_now = bar.timestamp + pd.Timedelta(minutes=1) - pd.Timedelta(minutes=1)  # bar open time
        self._sim_now = bar.timestamp
        self._last_lifecycle = lifecycle
        self._pending_bar = None
        self._pending_lifecycle = None
        return bar

    def _finalize_row(self, idx: int, now: datetime) -> Bar:
        ts = self._df.index[idx]
        bar = _row_to_bar(ts, self._df.iloc[idx])
        self.ingest_tick(bar, finalized=True, now=now)
        return bar

    def current_time(self) -> datetime:
        if self._sim_now is not None:
            return self._sim_now + pd.Timedelta(minutes=1) if self._pending_bar else self._sim_now
        return datetime.now(timezone.utc)

    def latest_bar(self) -> Bar | None:
        return self._cache.latest()

    def recent_bars(self, n: int) -> Sequence[Bar]:
        return self._cache.recent(n)

    def health(self) -> HealthReport:
        if self._connection == ConnectionState.DATA_DISCONNECTED:
            return HealthReport(DataHealth.DATA_MISSING, detail="DATA_DISCONNECTED")
        last = self._cache.latest()
        now = self.current_time()
        if last is None:
            return HealthReport(DataHealth.DATA_MISSING, current_time=now, detail="no closed bars")
        latency = (now - last.timestamp).total_seconds()
        if self._cache.duplicate_bars > 0:
            return HealthReport(DataHealth.DATA_OUT_OF_ORDER, last_bar_timestamp=last.timestamp, current_time=now, duplicate_bars=self._cache.duplicate_bars, detail="DATA_DUPLICATE")
        if self._cache.out_of_order_bars > 0:
            return HealthReport(DataHealth.DATA_OUT_OF_ORDER, last_bar_timestamp=last.timestamp, current_time=now, out_of_order_bars=self._cache.out_of_order_bars)
        if self._cache.gap_bars > 0:
            return HealthReport(DataHealth.DATA_GAP, last_bar_timestamp=last.timestamp, current_time=now, missing_bars=self._cache.gap_bars)
        if latency > self._staleness_limit:
            return HealthReport(DataHealth.DATA_STALE, last_bar_timestamp=last.timestamp, current_time=now, latency_seconds=latency)
        return HealthReport(DataHealth.DATA_HEALTHY, last_bar_timestamp=last.timestamp, current_time=now, latency_seconds=latency)

    def advance(self) -> bool:
        """Advance simulated live stream by one CLOSED bar."""
        next_i = self._i + 1
        if next_i >= len(self._df):
            return False
        self._i = next_i
        bar_end_time = self._df.index[next_i] + pd.Timedelta(minutes=1)
        self._finalize_row(next_i, bar_end_time.to_pydatetime().replace(tzinfo=timezone.utc))
        self._sim_now = bar_end_time.to_pydatetime().replace(tzinfo=timezone.utc)
        return True

    def atr(self, period: int = 14) -> float:
        return self._cache.atr(period or self._atr_period)

    def iter_closed_bars(self) -> Iterator[Bar]:
        while self.advance():
            bar = self.latest_bar()
            if bar:
                yield bar


def compare_replay_live_parity(df: pd.DataFrame, n_bars: int | None = None) -> tuple[bool, list[str]]:
    """Compare ReplayDataProvider vs StreamLiveDataProvider closed bars."""
    replay = ReplayDataProvider(df)
    live = StreamLiveDataProvider(df)
    live.connect()
    errors: list[str] = []
    max_bars = n_bars or len(df)

    def _compare(rb: Bar | None, lb: Bar | None, idx: int) -> None:
        if rb is None or lb is None:
            errors.append(f"bar {idx}: missing")
            return
        for field in ("open", "high", "low", "close", "volume"):
            rv = getattr(rb, field)
            lv = getattr(lb, field)
            if abs(rv - lv) > 1e-9:
                errors.append(f"bar {idx} {field}: replay={rv} live={lv}")
        if rb.timestamp != lb.timestamp:
            errors.append(f"bar {idx} ts: replay={rb.timestamp} live={lb.timestamp}")

    _compare(replay.latest_bar(), live.latest_bar(), 0)
    count = 1
    while count < max_bars:
        if not replay.advance() or not live.advance():
            break
        _compare(replay.latest_bar(), live.latest_bar(), count)
        if count > 14 and abs(replay.atr() - live.atr()) > 1e-6:
            errors.append(f"bar {count} atr: replay={replay.atr()} live={live.atr()}")
        count += 1
    return len(errors) == 0, errors


class DatabentoLiveProvider(StreamLiveDataProvider):
    """Optional Databento live adapter — requires DATABENTO_API_KEY."""

    def __init__(self, **kwargs) -> None:
        if not os.environ.get("DATABENTO_API_KEY"):
            raise RuntimeError("DATABENTO_API_KEY not set")
        super().__init__(**kwargs)
        # Phase74: streaming hook point for Phase74+ deployment; stream mode used for dress rehearsal
