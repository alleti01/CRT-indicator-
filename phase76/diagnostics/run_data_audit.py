#!/usr/bin/env python3
"""Phase76 checkpoint 00 — data availability audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase76.python.config import (  # noqa: E402
    CHECKPOINTS,
    CONTINUOUS_METHOD,
    PROFILE_TYPE,
    REPORTS,
    SOURCE,
    SYMBOL,
    TIMEZONE,
    TRADES_PILOT_PATH,
)
from phase76.python.data_loader import data_inventory, load_nq_1m  # noqa: E402


def main() -> int:
    df = load_nq_1m()
    inv = data_inventory(df)

    trades_pilot = TRADES_PILOT_PATH.exists() and TRADES_PILOT_PATH.stat().st_size > 1000
    research_level = 0
    if trades_pilot:
        research_level = 1

    audit = {
        "symbol": SYMBOL,
        "source": SOURCE,
        "continuous_methodology": CONTINUOUS_METHOD,
        "start": inv["start_utc"],
        "end": inv["end_utc"],
        "bars_1m": inv["bars"],
        "timezone_research": TIMEZONE,
        "timezone_storage": inv["timezone_storage"],
        "ohlcv": True,
        "trade_level": trades_pilot,
        "aggressor_side": trades_pilot,
        "volume_at_price_true": False,
        "quote_bbo": False,
        "depth": False,
        "research_level": research_level,
        "profile_reconstruction": PROFILE_TYPE,
        "loaded_paths": inv["loaded_paths"],
        "checkpoint_00": "PASS" if inv["bars"] > 100_000 else "FAIL",
    }

    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / "00_data_audit.json").write_text(json.dumps(audit, indent=2))

    md = [
        "# Phase76 — Data Audit",
        "",
        f"**Checkpoint 00:** `{audit['checkpoint_00']}`",
        "",
        "## Primary stack",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Symbol | {SYMBOL} |",
        f"| Source | {SOURCE} |",
        f"| Continuous | {CONTINUOUS_METHOD} |",
        f"| Start (UTC) | {audit['start']} |",
        f"| End (UTC) | {audit['end']} |",
        f"| 1m bars | {audit['bars_1m']:,} |",
        f"| Timezone (research) | {TIMEZONE} |",
        f"| Research level | **LEVEL {research_level}** |",
        "",
        "## Availability",
        "",
        "| Data type | Available |",
        "|-----------|-----------|",
        f"| 1m OHLCV | Yes |",
        f"| Trade prints | {'Yes (pilot Jan 2024 only)' if trades_pilot else 'No'} |",
        f"| Aggressor side | {'Yes (pilot)' if trades_pilot else 'No'} |",
        f"| TRUE volume-at-price | **No** |",
        f"| BBO / quotes | No |",
        f"| Depth (MBP/MBO) | No |",
        "",
        "## Profile reconstruction",
        "",
        f"All VAH/VAL/POC/HVN/LVN use **`{PROFILE_TYPE}`** — volume uniformly distributed across each bar's high–low range.",
        "",
        "This is **not** exact volume-at-price. Never treat as TRUE_PROFILE.",
        "",
        "## Loaded files",
        "",
    ]
    for p in audit["loaded_paths"]:
        md.append(f"- `{p}`")
    md.extend(
        [
            "",
            "## Order-flow gate (Phase76-OF)",
            "",
            "Blocked until an auction family survives information gates. Full-history trades not available.",
            "",
        ]
    )
    (REPORTS / "PHASE76_DATA_AUDIT.md").write_text("\n".join(md) + "\n")
    print(json.dumps(audit, indent=2))
    print(f"Report: {REPORTS / 'PHASE76_DATA_AUDIT.md'}")
    return 0 if audit["checkpoint_00"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
