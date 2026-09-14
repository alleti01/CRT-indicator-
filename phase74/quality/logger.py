"""Append-only quality gate decisions (skip or take)."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase74.quality.gates import QualityDecision

_FIELDS = [
    "received_at_utc",
    "signal_id",
    "direction",
    "decision",
    "reason",
    "atr",
    "box",
    "box_atr",
    "progress_atr",
    "range_low",
    "range_high",
    "close",
    "percentile_in_box",
]


class QualitySkipLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = log_dir / "quality_skips.jsonl"
        self.csv_path = log_dir / "quality_skips.csv"

    def log(
        self,
        decision: QualityDecision,
        *,
        signal_id: str,
        direction: str,
        received_at: datetime | None = None,
    ) -> None:
        received_at = received_at or datetime.now(timezone.utc)
        row: dict[str, Any] = {
            "received_at_utc": received_at.isoformat(),
            "signal_id": signal_id,
            "direction": direction,
            "decision": decision.decision,
            "reason": decision.reason,
            "atr": decision.atr,
            "box": decision.box,
            "box_atr": decision.box_atr,
            "progress_atr": decision.progress_atr,
            "range_low": decision.range_low,
            "range_high": decision.range_high,
            "close": decision.close,
            "percentile_in_box": decision.percentile_in_box,
        }
        with self.jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
        write_header = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        with self.csv_path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=_FIELDS)
            if write_header:
                w.writeheader()
            w.writerow(row)
