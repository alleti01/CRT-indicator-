"""Append-only execution ledger. Never logs secrets."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def safe_account_id(account: str) -> str:
    if not account:
        return ""
    if len(account) <= 4:
        return "***"
    return "***" + account[-4:]


@dataclass
class LedgerRow:
    event_id: str = ""
    signal_id: str = ""
    command_id: str = ""
    signal_time_utc: str = ""
    webhook_received_utc: str = ""
    decision_time_utc: str = ""
    command_created_utc: str = ""
    direction: str = ""
    instrument: str = ""
    quantity: int = 0
    account_safe_id: str = ""
    expected_entry: float | None = None
    ninjatrader_order_id: str = ""
    submit_time: str = ""
    ack_time: str = ""
    fill_time: str = ""
    fill_price: float | None = None
    fill_quantity: int | None = None
    risk_R: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    stop_order_id: str = ""
    target_order_id: str = ""
    stop_working_time: str = ""
    target_working_time: str = ""
    exit_time: str = ""
    exit_price: float | None = None
    exit_reason: str = ""
    slippage_ticks: float | None = None
    slippage_points: float | None = None
    final_position: str = ""
    reconciliation_status: str = ""
    execution_mode: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class ExecutionLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: list[LedgerRow] = []

    def append(self, row: LedgerRow) -> LedgerRow:
        self.rows.append(row)
        payload = asdict(row)
        extra = payload.pop("extra", {}) or {}
        payload.update(extra)
        # never persist obvious secret keys
        for key in list(payload):
            if "token" in key.lower() or "secret" in key.lower() or "password" in key.lower():
                payload.pop(key)
        with self.path.open("a") as fh:
            fh.write(json.dumps(payload) + "\n")
        return row

    def update_last(self, **fields: Any) -> LedgerRow | None:
        if not self.rows:
            return None
        row = self.rows[-1]
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
            else:
                row.extra[key] = value
        with self.path.open("a") as fh:
            payload = asdict(row)
            extra = payload.pop("extra", {}) or {}
            payload.update(extra)
            payload["_amend"] = True
            fh.write(json.dumps(payload) + "\n")
        return row
