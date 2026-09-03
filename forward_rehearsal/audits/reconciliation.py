"""Signal reconciliation and audit reports."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


RECONCILIATION_FIELDS = [
    "signal_id",
    "tv_timestamp",
    "webhook_timestamp",
    "market_bar_timestamp",
    "direction",
    "signal_price",
    "atr",
    "engine_action",
    "reason",
    "latency_ms",
    "status",
]


@dataclass
class ReconciliationRow:
    signal_id: str
    tv_timestamp: str
    webhook_timestamp: str
    market_bar_timestamp: str
    direction: str
    signal_price: float
    atr: float
    engine_action: str
    reason: str
    latency_ms: float
    status: str


@dataclass
class SignalReconciler:
    rows: list[ReconciliationRow] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)

    def record(
        self,
        *,
        signal_id: str,
        tv_timestamp: datetime,
        webhook_timestamp: datetime,
        market_bar_timestamp: datetime | None,
        direction: str,
        signal_price: float,
        atr: float,
        engine_action: str,
        reason: str,
        latency_ms: float,
        rejected: bool = False,
        error: bool = False,
    ) -> ReconciliationRow:
        if signal_id in self._seen and not rejected:
            status = "DUPLICATE"
        elif rejected:
            status = "REJECTED_VALIDLY" if reason else "REJECTED_VALIDLY"
        elif error:
            status = "ERROR"
        elif "STALE" in reason.upper():
            status = "STALE"
        elif not engine_action:
            status = "MISSING"
        else:
            status = "MATCH"
            self._seen.add(signal_id)

        row = ReconciliationRow(
            signal_id=signal_id,
            tv_timestamp=tv_timestamp.isoformat(),
            webhook_timestamp=webhook_timestamp.isoformat(),
            market_bar_timestamp=market_bar_timestamp.isoformat() if market_bar_timestamp else "",
            direction=direction,
            signal_price=signal_price,
            atr=atr,
            engine_action=engine_action,
            reason=reason,
            latency_ms=latency_ms,
            status=status,
        )
        self.rows.append(row)
        return row

    def write_csv(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=RECONCILIATION_FIELDS)
            w.writeheader()
            for row in self.rows:
                w.writerow({k: getattr(row, k) for k in RECONCILIATION_FIELDS})

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        return {
            "total": len(self.rows),
            "by_status": counts,
            "unique_signals": len(self._seen),
            "duplicates": counts.get("DUPLICATE", 0),
            "missing": counts.get("MISSING", 0),
        }
