"""Completed paper trade journal."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TradeJournalEntry:
    trade_id: str
    pine_signal_id: str
    direction: str
    signal_timestamp: str
    signal_price: float
    entry_timestamp: str
    fill_price: float
    atr: float
    stop: float
    target: float
    exit_timestamp: str = ""
    exit_price: float | None = None
    exit_reason: str = ""
    gross_R: float | None = None
    estimated_costs: float = 0.0
    net_R: float | None = None
    MFE: float = 0.0
    MAE: float = 0.0
    hold_time_minutes: float = 0.0
    signal_to_fill_ms: float = 0.0
    slippage_points: float = 0.0
    slippage_ticks: float = 0.0
    slippage_R: float = 0.0
    data_health_incidents: int = 0
    execution_incidents: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class TradeJournal:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl = log_dir / "paper_trades.jsonl"
        self._csv = log_dir / "paper_trades.csv"
        self._open: dict[str, TradeJournalEntry] = {}

    def open_trade(self, entry: TradeJournalEntry) -> None:
        self._open[entry.trade_id] = entry

    def close_trade(self, trade_id: str, **updates) -> None:
        rec = self._open.pop(trade_id, None)
        if not rec:
            return
        for k, v in updates.items():
            if hasattr(rec, k):
                setattr(rec, k, v)
        payload = asdict(rec)
        with self._jsonl.open("a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
        write_header = not self._csv.exists() or self._csv.stat().st_size == 0
        with self._csv.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[k for k in payload if k != "extra"])
            if write_header:
                w.writeheader()
            w.writerow({k: payload[k] for k in w.fieldnames})
