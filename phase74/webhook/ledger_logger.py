"""Append-only log for Phase72A signal ledger alert() JSON (diagnostic, no trading)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class LedgerAlertLogger:
    """Log ledger webhook payloads to jsonl + flattened csv (gate_state columns)."""

    _CSV_FIELDS = [
        "received_at_utc",
        "event_id",
        "event",
        "direction",
        "symbol",
        "signal_bar_time_utc_ms",
        "bar_index",
        "close",
        "atr",
        "pine_hash",
        "htf_warmup_ready",
        "armed_long",
        "armed_short",
        "evidence_threshold_long",
        "evidence_threshold_short",
        "arm_total_long_prov",
        "arm_total_short_prov",
        "pass_reason_code",
        "decide_e_long",
        "decide_e_short",
        "p4_keep_long",
        "p4_keep_short",
        "h1_keep_long",
        "h1_keep_short",
        "gate_open",
        "not_in_cooldown",
        "take_long",
        "take_short",
    ]

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.log_dir / "ledger_alerts.jsonl"
        self.csv_path = self.log_dir / "ledger_alerts.csv"

    def log(self, payload: dict[str, Any], received_at: datetime | None = None) -> None:
        received_at = received_at or datetime.now(timezone.utc)
        gate = payload.get("gate_state") or {}
        if isinstance(gate, str):
            try:
                gate = json.loads(gate)
            except json.JSONDecodeError:
                gate = {}

        record = {
            "received_at_utc": received_at.isoformat(),
            "payload": payload,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

        row = {
            "received_at_utc": received_at.isoformat(),
            "event_id": payload.get("event_id", ""),
            "event": payload.get("event", ""),
            "direction": payload.get("direction", ""),
            "symbol": payload.get("symbol", ""),
            "signal_bar_time_utc_ms": payload.get("signal_bar_time_utc_ms", ""),
            "bar_index": payload.get("bar_index", ""),
            "close": payload.get("close", ""),
            "atr": payload.get("atr", ""),
            "pine_hash": payload.get("pine_hash", ""),
        }
        for key in self._CSV_FIELDS:
            if key in row:
                continue
            row[key] = gate.get(key, "")

        write_header = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self._CSV_FIELDS, extrasaction="ignore")
            if write_header:
                w.writeheader()
            w.writerow(row)
