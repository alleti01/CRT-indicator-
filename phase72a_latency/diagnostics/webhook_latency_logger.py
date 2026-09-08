"""Optional webhook latency logger — does NOT modify TraderEngine.

Wrap any receiver handle_payload to append python_received_utc to a CSV log.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

LOG_PATH = Path(__file__).resolve().parents[1] / "reports" / "webhook_receive_log.csv"


def log_receipt(payload: dict, received_at: datetime | None = None) -> datetime:
    received_at = received_at or datetime.now(timezone.utc)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_PATH.exists()
    with LOG_PATH.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow([
                "python_received_utc",
                "event",
                "event_id",
                "signal_bar_time",
                "entry_bar_time",
                "alert_generated_time",
                "raw_json",
            ])
        w.writerow([
            received_at.isoformat(),
            payload.get("event", ""),
            payload.get("event_id", payload.get("signal_id", "")),
            payload.get("signal_bar_time_utc", payload.get("signal_bar_time_ms", "")),
            payload.get("entry_bar_time_ms", payload.get("entry_bar_time_utc", "")),
            payload.get("alert_generated_time_ms", payload.get("signal_time_utc", "")),
            json.dumps(payload, separators=(",", ":")),
        ])
    return received_at


def wrap_handler(handler: Callable) -> Callable:
    """Decorator for webhook handlers — logging only."""

    def wrapped(payload: dict, *args, **kwargs):
        received = log_receipt(payload)
        payload = {**payload, "_python_received_utc": received.isoformat()}
        return handler(payload, *args, **kwargs)

    return wrapped
