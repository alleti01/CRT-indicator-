"""Decision and event logging."""
from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DecisionRecord:
    timestamp_utc: str
    market_timestamp: str = ""
    signal_id: str = ""
    symbol: str = "NQ"
    state_before: str = ""
    state_after: str = ""
    pine_event: str = ""
    pine_direction: str = ""
    pine_signal_price: float | None = None
    pine_atr: float | None = None
    current_price: float | None = None
    current_atr: float | None = None
    position: str = "FLAT"
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    current_R: float | None = None
    MFE_R: float | None = None
    MAE_R: float | None = None
    bars_in_trade: int = 0
    minutes_in_trade: float = 0.0
    market_data_health: str = ""
    action: str = ""
    reason_code: str = ""
    order_id: str = ""
    order_action: str = ""
    order_status: str = ""
    fill_price: float | None = None
    latency_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DecisionLogger:
    FIELDS = [f.name for f in DecisionRecord.__dataclass_fields__.values() if f.name != "extra"]

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._jsonl = log_dir / "decisions.jsonl"
        self._csv = log_dir / "decisions.csv"
        self._csv_initialized = self._csv.exists() and self._csv.stat().st_size > 0

    def log(self, rec: DecisionRecord) -> None:
        payload = asdict(rec)
        extra = payload.pop("extra", {})
        if extra:
            payload.update(extra)
        with self._jsonl.open("a") as f:
            f.write(json.dumps(payload, default=str) + "\n")
        with self._csv.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=self.FIELDS, extrasaction="ignore")
            if not self._csv_initialized:
                w.writeheader()
                self._csv_initialized = True
            w.writerow({k: payload.get(k, "") for k in self.FIELDS})

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
