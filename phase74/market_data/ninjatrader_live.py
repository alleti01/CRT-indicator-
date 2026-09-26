"""NinjaTrader 8 live 1m NQ bar provider — read-only localhost bridge."""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from phase73.market_data.bar import Bar
from phase73.market_data.health import DataHealth, HealthReport
from phase74.contracts.mapping import validate_ninjatrader_contract
from phase74.market_data.connection import ConnectionState
from phase74.market_data.live_provider import StreamLiveDataProvider
from phase74.market_data.ninjatrader.bridge_server import BridgeStats, NinjaTraderBridgeServer

log = logging.getLogger("phase74.ninjatrader.live")


def load_closed_bars_csv(path: Path, limit: int = 20) -> list[Bar]:
    """Last `limit` closed bars from BarLogger CSV (mid-session restart seed)."""
    if not path.exists():
        return []
    rows: list[Bar] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                ts = datetime.fromisoformat(str(row["timestamp_utc"]).replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                rows.append(
                    Bar(
                        ts,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row.get("volume") or 0.0),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
    return rows[-limit:]


class NinjaTraderLiveDataProvider(StreamLiveDataProvider):
    """
    Push-driven live provider: NinjaTrader CRTBarBridge → localhost TCP → closed 1m bars.
    Fail-closed on auth failure, disconnect, contract mismatch, or ATR bootstrap incomplete.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        auth_token: str = "",
        bootstrap_bars: int = 15,
        expected_contract_prefix: str = "NQ",
        on_bar: Callable[[Bar], None] | None = None,
        preserve_bars_on_disconnect: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(None, **kwargs)
        self._host = host
        self._port = port
        self._auth_token = auth_token or os.environ.get("NINJATRADER_BRIDGE_TOKEN", "")
        self._bootstrap_bars = bootstrap_bars
        self._expected_contract_prefix = expected_contract_prefix
        self._on_bar = on_bar
        self._preserve_bars_on_disconnect = preserve_bars_on_disconnect
        self._server: NinjaTraderBridgeServer | None = None
        self._contract = ""
        self._was_connected = False
        self._last_bridge_stats: BridgeStats | None = None

    @property
    def contract_identity(self) -> str | None:
        return self._contract or None

    @property
    def atr_ready(self) -> bool:
        bars = self._cache.recent(self._bootstrap_bars + 1)
        return len(bars) >= self._bootstrap_bars and self._cache.atr(self._atr_period) > 0

    @property
    def bridge_stats(self) -> BridgeStats | None:
        return self._last_bridge_stats

    def connect(self) -> None:
        if not self._auth_token:
            raise RuntimeError("NINJATRADER_BRIDGE_TOKEN not set — required for NinjaTrader bridge")
        was_disconnected = self._connection == ConnectionState.DATA_DISCONNECTED
        trust_localhost = os.environ.get("NINJATRADER_BRIDGE_TRUST_LOCALHOST", "").lower() in (
            "1",
            "true",
            "yes",
        )
        self._server = NinjaTraderBridgeServer(
            self._host,
            self._port,
            auth_token=self._auth_token,
            on_bar=self._handle_bar,
            on_authenticated=self._handle_authenticated,
            on_disconnect=self._handle_disconnect,
            trust_localhost=trust_localhost,
        )
        self._server.start()
        if was_disconnected and not self._was_connected:
            self._connection = ConnectionState.DATA_CONNECTED
        log.info(
            "ninjatrader bridge server started host=%s port=%s bootstrap_bars=%s",
            self._host,
            self._port,
            self._bootstrap_bars,
        )

    def seed_closed_bars(self, bars: Sequence[Bar]) -> int:
        """Load already-closed bars so ATR is ready after a mid-session restart."""
        n = 0
        for bar in bars:
            self._cache.append(bar)
            self._sim_now = bar.timestamp + timedelta(minutes=1)
            n += 1
        if n:
            log.info("ninjatrader seeded %s closed bars last=%s", n, bars[-1].timestamp.isoformat())
        return n

    def _reset_bar_cache(self) -> None:
        self._cache.clear()
        self._cache.gap_bars = 0
        self._cache.duplicate_bars = 0
        self._cache.out_of_order_bars = 0
        self._sim_now = None

    def _recent_window_has_gap(self) -> bool:
        bars = self._cache.recent(self._bootstrap_bars)
        for prev, cur in zip(bars, bars[1:]):
            delta_min = (cur.timestamp - prev.timestamp).total_seconds() / 60.0
            if delta_min > 1.5:
                return True
        return False

    def _handle_authenticated(self, contract: str) -> None:
        err = validate_ninjatrader_contract(contract, self._expected_contract_prefix)
        if err:
            log.error("ninjatrader contract rejected: %s", err)
            self._connection = ConnectionState.DATA_DISCONNECTED
            return
        if self._contract and self._contract != contract:
            log.info("ninjatrader contract changed %s -> %s — reset bar cache", self._contract, contract)
            self._reset_bar_cache()
        self._contract = contract
        self._was_connected = True
        self._connection = ConnectionState.DATA_RECONNECTED if self._cache.latest() else ConnectionState.DATA_CONNECTED
        log.info("ninjatrader authenticated contract=%s", contract)

    def _handle_disconnect(self) -> None:
        n = len(self._cache.recent(10_000))
        log.warning(
            "ninjatrader bridge disconnected — fail-closed (preserve_bars=%s bars=%s)",
            self._preserve_bars_on_disconnect,
            n,
        )
        self._connection = ConnectionState.DATA_DISCONNECTED
        if not self._preserve_bars_on_disconnect:
            self._cache.clear()
            self._sim_now = None
            self._contract = ""

    def _handle_bar(self, bar: Bar, stats: BridgeStats) -> None:
        self._last_bridge_stats = stats
        bar_end = bar.timestamp + timedelta(minutes=1)
        end_dt = bar_end.replace(tzinfo=timezone.utc)
        finalized = self.ingest_tick(bar, finalized=True, now=end_dt)
        if finalized:
            self._sim_now = end_dt
            self._connection = ConnectionState.DATA_CONNECTED
            log.debug(
                "ninjatrader bar seq=%s ts=%s latency_ms=%.1f",
                stats.last_seq,
                bar.timestamp.isoformat(),
                stats.last_bar_latency_ms,
            )
            if self._on_bar:
                self._on_bar(finalized)

    def disconnect(self) -> None:
        if self._server:
            self._server.stop()
            self._server = None
        super().disconnect()

    def health(self) -> HealthReport:
        if self._connection == ConnectionState.DATA_DISCONNECTED:
            return HealthReport(DataHealth.DATA_MISSING, detail="DATA_DISCONNECTED")
        if self._server is None or not self._server.is_connected:
            return HealthReport(DataHealth.DATA_MISSING, detail="NT_CLIENT_NOT_CONNECTED")
        last = self._cache.latest()
        now = self.current_time()
        if last is None:
            return HealthReport(DataHealth.DATA_MISSING, current_time=now, detail="no closed bars")
        if self._cache.duplicate_bars > 0:
            return HealthReport(
                DataHealth.DATA_OUT_OF_ORDER,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                duplicate_bars=self._cache.duplicate_bars,
                detail="DATA_DUPLICATE",
            )
        if self._cache.out_of_order_bars > 0:
            return HealthReport(
                DataHealth.DATA_OUT_OF_ORDER,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                out_of_order_bars=self._cache.out_of_order_bars,
            )
        if self._recent_window_has_gap():
            return HealthReport(
                DataHealth.DATA_GAP,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                missing_bars=self._cache.gap_bars,
                detail="RECENT_WINDOW_GAP",
            )
        latency = (now - last.timestamp).total_seconds()
        if latency > self._staleness_limit:
            return HealthReport(
                DataHealth.DATA_STALE,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                latency_seconds=latency,
            )
        if not self.atr_ready:
            return HealthReport(
                DataHealth.DATA_MISSING,
                last_bar_timestamp=last.timestamp,
                current_time=now,
                detail="ATR_BOOTSTRAP",
            )
        if self._contract:
            err = validate_ninjatrader_contract(self._contract, self._expected_contract_prefix)
            if err:
                return HealthReport(DataHealth.DATA_MISSING, detail=err)
        return HealthReport(
            DataHealth.DATA_HEALTHY,
            last_bar_timestamp=last.timestamp,
            current_time=now,
            latency_seconds=latency,
        )

    def advance(self) -> bool:
        """Live provider is push-driven; advance is a no-op."""
        return False
