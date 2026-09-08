#!/usr/bin/env python3
"""Phase72A-LATENCY — analyze webhook/event timing from logs."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "phase72a_latency" / "reports"


def parse_webhook_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(dict(row))
    return rows


def analyze_latency(rows: list[dict]) -> pd.DataFrame:
    import pandas as pd

    out = []
    for row in rows:
        outcome = row.get("outcome") or row.get("status") or ""
        if "ACCEPT" not in outcome.upper() and outcome != "WEBHOOK_VALID":
            continue
        event = row.get("event") or row.get("Event") or ""
        ts_str = row.get("Time (ET)") or row.get("received_at") or row.get("time") or ""
        out.append({
            "event": event,
            "received_time": ts_str,
            "outcome": outcome,
        })
    return pd.DataFrame(out)


def main() -> None:
    import pandas as pd

    REPORTS.mkdir(parents=True, exist_ok=True)

    webhook_path = ROOT / "forward_rehearsal" / "reports" / "WEBHOOK_ALERTS_FULL.csv"
    rows = parse_webhook_csv(webhook_path)

    if not rows:
        # Build from analysis doc timestamps
        summary = pd.DataFrame([
            {"event": "SIGNAL_LONG", "note": "Alerts fire at bar close (:59 suffix typical)"},
            {"event": "SIGNAL_SHORT", "note": "Production webhooks use SIGNAL not ENTER"},
        ])
        summary.to_csv(REPORTS / "LATENCY_BREAKDOWN.csv", index=False)
        print(f"No webhook CSV at {webhook_path}; wrote summary stub")
        return

    df = pd.DataFrame(rows)
    breakdown_path = REPORTS / "LATENCY_BREAKDOWN.csv"
    df.to_csv(breakdown_path, index=False)
    print(f"Wrote {breakdown_path} ({len(df)} rows)")

    # Live parity stub — populate during shadow test
    live_path = REPORTS / "LIVE_EVENT_PARITY.csv"
    if not live_path.exists():
        pd.DataFrame(columns=[
            "event_id", "direction", "chart_enter_time", "alert_payload_entry_time",
            "python_received_utc", "pine_entry_to_python_ms", "pass_fail",
        ]).to_csv(live_path, index=False)
        print(f"Created empty {live_path} for live shadow collection")


if __name__ == "__main__":
    main()
