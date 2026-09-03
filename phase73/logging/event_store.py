"""Persistent CSV/JSONL event stores."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class EventStore:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def append(self, name: str, row: dict[str, Any]) -> None:
        jsonl = self.log_dir / f"{name}.jsonl"
        with jsonl.open("a") as f:
            f.write(json.dumps(row, default=str) + "\n")
        csv_path = self.log_dir / f"{name}.csv"
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if write_header:
                w.writeheader()
            w.writerow(row)

    def log_signal(self, row: dict[str, Any]) -> None:
        self.append("signals", row)

    def log_order(self, row: dict[str, Any]) -> None:
        self.append("orders", row)

    def log_fill(self, row: dict[str, Any]) -> None:
        self.append("fills", row)

    def log_position(self, row: dict[str, Any]) -> None:
        self.append("positions", row)

    def log_error(self, row: dict[str, Any]) -> None:
        self.append("errors", row)
