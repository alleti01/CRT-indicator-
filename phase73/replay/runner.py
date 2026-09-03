"""Replay engine — same TraderEngine as production."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator

import pandas as pd

from phase73.config.loader import Phase73Config, load_config
from phase73.execution.sim_router import SimOrderRouter
from phase73.logging.decision_logger import DecisionLogger
from phase73.logging.event_store import EventStore
from phase73.market_data.provider import ReplayDataProvider
from phase73.persistence.state import StatePersistence
from phase73.trader.engine import TraderEngine
from phase73.webhook.schemas import PineSignal, make_test_signal


def _synthetic_bars(n: int = 200, start: datetime | None = None) -> pd.DataFrame:
    start = start or datetime(2026, 8, 30, 17, 0, tzinfo=timezone.utc)
    idx = pd.date_range(start, periods=n, freq="1min", tz="UTC")
    prices = 20000.0
    rows = []
    for i, ts in enumerate(idx):
        o = prices
        c = prices + (1 if i % 2 == 0 else -1) * 2.5
        h = max(o, c) + 1.0
        l = min(o, c) - 1.0
        rows.append({"open": o, "high": h, "low": l, "close": c, "volume": 100})
        prices = c
    return pd.DataFrame(rows, index=idx)


def load_replay_dataframe(path: Path | None = None) -> pd.DataFrame:
    if path is None:
        return _synthetic_bars()
    return pd.read_csv(path, parse_dates=["timestamp"], index_col="timestamp")


class ReplayRunner:
    def __init__(
        self,
        cfg: Phase73Config | None = None,
        df: pd.DataFrame | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self.cfg = cfg or load_config()
        if log_dir:
            self.cfg.raw.setdefault("logging", {})["log_dir"] = str(log_dir)
        self.df = df if df is not None else _synthetic_bars()
        self.provider = ReplayDataProvider(self.df, staleness_limit_seconds=self.cfg.staleness_limit_seconds)
        self.router = SimOrderRouter()
        log_dir_path = self.cfg.log_dir
        self.engine = TraderEngine(
            cfg=self.cfg,
            market_data=self.provider,
            router=self.router,
            logger=DecisionLogger(log_dir_path),
            events=EventStore(log_dir_path),
            persistence=StatePersistence(self.cfg.state_file),
        )

    def inject_signal(self, signal: PineSignal) -> dict:
        from phase73.webhook.schemas import WebhookReason

        return self.engine.on_webhook_signal(signal, WebhookReason.WEBHOOK_VALID)

    def run_bars(self, n: int | None = None) -> int:
        count = 0
        while n is None or count < n:
            self.engine.on_bar()
            if not self.provider.advance():
                break
            count += 1
        return count

    def run_signals(self, signals: list[PineSignal]) -> list[dict]:
        results = []
        sig_iter: Iterator[PineSignal] = iter(signals)
        next_sig = next(sig_iter, None)
        while True:
            bar = self.provider.latest_bar()
            if bar and next_sig and bar.timestamp >= next_sig.signal_bar_time_utc:
                results.append(self.inject_signal(next_sig))
                next_sig = next(sig_iter, None)
            self.engine.on_bar()
            if not self.provider.advance():
                if next_sig:
                    results.append(self.inject_signal(next_sig))
                break
        return results
