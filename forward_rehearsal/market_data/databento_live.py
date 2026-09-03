"""Databento live NQ 1-minute bar provider."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Callable

import pandas as pd

from phase73.market_data.bar import Bar
from phase74.market_data.connection import ConnectionState
from phase74.market_data.live_provider import StreamLiveDataProvider

log = logging.getLogger("forward.databento")


def _ns_to_utc(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1_000_000_000, tz=timezone.utc)


def _record_to_bar(record) -> Bar | None:
    """Convert Databento OHLCV record to Bar (minute open timestamp)."""
    try:
        ts_ns = int(getattr(record, "ts_event", 0) or getattr(record, "hd", {}).ts_event)
        if ts_ns <= 0:
            return None
        ts = _ns_to_utc(ts_ns)
        # ohlcv-1m ts_event is bar open; align to minute floor
        ts = ts.replace(second=0, microsecond=0)
        o = float(getattr(record, "open", 0)) / 1e9 if getattr(record, "open", 0) > 1e6 else float(getattr(record, "open", 0))
        h = float(getattr(record, "high", 0)) / 1e9 if getattr(record, "high", 0) > 1e6 else float(getattr(record, "high", 0))
        l = float(getattr(record, "low", 0)) / 1e9 if getattr(record, "low", 0) > 1e6 else float(getattr(record, "low", 0))
        c = float(getattr(record, "close", 0)) / 1e9 if getattr(record, "close", 0) > 1e6 else float(getattr(record, "close", 0))
        v = float(getattr(record, "volume", 0))
        return Bar(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)
    except Exception as exc:
        log.warning("record parse failed: %s", exc)
        return None


class DatabentoLiveProvider(StreamLiveDataProvider):
    """
    Live NQ 1m bars via Databento GLBX.MDP3 ohlcv-1m.
    Requires DATABENTO_API_KEY in environment — never logged.
    """

    def __init__(
        self,
        *,
        dataset: str = "GLBX.MDP3",
        schema: str = "ohlcv-1m",
        symbol: str = "NQ.v.0",
        stype_in: str = "continuous",
        on_bar: Callable[[Bar], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(None, **kwargs)
        self._dataset = dataset
        self._schema = schema
        self._symbol = symbol
        self._stype_in = stype_in
        self._on_bar = on_bar
        self._client = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_bar_ts: datetime | None = None

    def connect(self) -> None:
        key = os.environ.get("DATABENTO_API_KEY")
        if not key:
            raise RuntimeError("DATABENTO_API_KEY not set — required for forward rehearsal live data")
        try:
            import databento as db
        except ImportError as exc:
            raise RuntimeError("install databento package for live streaming") from exc

        self._connection = ConnectionState.DATA_CONNECTED
        self._client = db.Live(key=key)

        def _run() -> None:
            try:
                self._client.subscribe(
                    dataset=self._dataset,
                    schema=self._schema,
                    symbols=self._symbol,
                    stype_in=self._stype_in,
                )
                self._client.add_callback(self._handle_record)
                self._client.start()
                self._client.block_for_close()
            except Exception as exc:
                log.error("databento stream error: %s", type(exc).__name__)
                self._connection = ConnectionState.DATA_DISCONNECTED
            finally:
                self._connection = ConnectionState.DATA_DISCONNECTED

        self._thread = threading.Thread(target=_run, daemon=True, name="databento-live")
        self._thread.start()
        log.info("databento live connected dataset=%s symbol=%s", self._dataset, self._symbol)

    def _handle_record(self, record) -> None:
        if self._stop.is_set():
            return
        bar = _record_to_bar(record)
        if bar is None:
            return
        if self._last_bar_ts and bar.timestamp <= self._last_bar_ts:
            return
        bar_end = bar.timestamp + pd.Timedelta(minutes=1)
        finalized = self.ingest_tick(bar, finalized=True, now=bar_end.to_pydatetime().replace(tzinfo=timezone.utc))
        if finalized:
            self._last_bar_ts = bar.timestamp
            self._sim_now = bar_end.to_pydatetime().replace(tzinfo=timezone.utc)
            if self._on_bar:
                self._on_bar(finalized)

    def disconnect(self) -> None:
        self._stop.set()
        if self._client is not None:
            try:
                self._client.stop()
            except Exception:
                pass
        super().disconnect()

    def advance(self) -> bool:
        """Live provider is push-driven; advance is a no-op."""
        return False
