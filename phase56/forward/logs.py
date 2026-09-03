"""Append-only forward log writers."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


class AppendOnlyLog:
    """CSV log that only appends; never rewrites prior rows."""

    def __init__(self, path: Path, fieldnames: list[str]):
        self.path = path
        self.fieldnames = fieldnames
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    def read_df(self) -> pd.DataFrame:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return pd.DataFrame(columns=self.fieldnames)
        return pd.read_csv(self.path)

    def last_value(self, col: str, default=None):
        df = self.read_df()
        if df.empty or col not in df.columns:
            return default
        return df[col].iloc[-1]

    def count(self) -> int:
        return len(self.read_df())

    def append(self, row: dict) -> None:
        clean = {k: row.get(k, "") for k in self.fieldnames}
        with self.path.open("a", newline="") as f:
            csv.DictWriter(f, fieldnames=self.fieldnames).writerow(clean)


EVENT_FIELDS = [
    "event_id",
    "timestamp_ct",
    "timestamp_utc",
    "direction",
    "event_type",
    "quality_score",
    "D10_pass",
    "episode_status",
    "episode_id",
    "suppressed_same_direction",
    "suppression_until",
    "core_authorized",
    "core_b1_active",
    "model_hash",
]

SIGNAL_FIELDS = [
    "signal_id",
    "episode_id",
    "timestamp_ct",
    "timestamp_utc",
    "direction",
    "initiating_event_id",
    "event_type",
    "quality_score",
    "entry_timestamp",
    "entry_price",
    "atr",
    "stop_price",
    "target_price",
    "planned_max_hold_minutes",
    "core_authorized",
    "core_signal_active",
    "model_hash",
    "explanation",
]

TRADE_FIELDS = [
    "signal_id",
    "episode_id",
    "direction",
    "entry_timestamp",
    "entry_price",
    "exit_timestamp",
    "exit_price",
    "exit_reason",
    "gross_R",
    "cost_R",
    "net_R",
    "MFE_R",
    "MAE_R",
    "duration_minutes",
    "core_authorized",
    "model_hash",
]

AUDIT_FIELDS = [
    "timestamp_ct",
    "audit_type",
    "detail",
    "model_hash",
]

DAILY_HASH_FIELDS = [
    "date",
    "model_hash",
    "implementation_hash",
    "data_end_timestamp",
    "event_count",
    "signal_count",
    "trade_count",
    "cumulative_net_R",
]
