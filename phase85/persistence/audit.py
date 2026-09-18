"""Structured audit log. Never writes secrets."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

AUDIT_EVENTS = frozenset(
    {
        "EXECUTION_BRIDGE_STARTED",
        "EXECUTION_CONNECTED",
        "EXECUTION_AUTHENTICATED",
        "ACCOUNT_VERIFIED",
        "FUNDED_ACCOUNT_VERIFIED",
        "CONTRACT_VERIFIED",
        "POSITION_RECONCILED",
        "ORDERS_RECONCILED",
        "EXECUTION_READY_SIM",
        "EXECUTION_READY_FUNDED",
        "COMMAND_RECEIVED",
        "COMMAND_REJECTED",
        "ORDER_SUBMITTED",
        "ORDER_ACCEPTED",
        "ORDER_REJECTED",
        "PARTIAL_FILL",
        "FILL",
        "PROTECTION_SUBMITTED",
        "PROTECTION_WORKING",
        "PROTECTION_FAILURE",
        "STOP_FILLED",
        "TARGET_FILLED",
        "POSITION_FLAT",
        "RECONCILIATION_FAIL",
        "EXECUTION_HALTED",
        "WOULD_ENTER",
        "INVALID_TRANSITION",
    }
)


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.events: list[dict[str, Any]] = []

    def write(self, name: str, **fields: Any) -> dict[str, Any]:
        cleaned = {k: v for k, v in fields.items() if "token" not in k.lower() and "secret" not in k.lower()}
        cleaned.pop("event", None)
        rec = {
            "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "event": name,
            **cleaned,
        }
        self.events.append(rec)
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        return rec
