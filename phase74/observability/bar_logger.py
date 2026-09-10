"""Append closed 1m bars to CSV for accurate post-session replay."""
from __future__ import annotations

import csv
from pathlib import Path

from phase73.market_data.bar import Bar


class BarLogger:
    FIELDS = [
        "timestamp_utc",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "atr",
        "market_data_health",
    ]

    def __init__(self, log_dir: Path) -> None:
        self.path = log_dir / "bars.csv"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=self.FIELDS).writeheader()

    def log(self, bar: Bar, *, atr: float = 0.0, health: str = "DATA_HEALTHY") -> None:
        row = {
            "timestamp_utc": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "atr": atr,
            "market_data_health": health,
        }
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.FIELDS).writerow(row)
