#!/usr/bin/env python3
"""Compare paper journal gross R vs sequential replay for a UTC day."""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase74.replay.sequential import sequential_replay

LOGS = ROOT / "phase74" / "logs"
ET = ZoneInfo("America/New_York")


def paper_trades_for_day(day: str) -> list[dict]:
    path = LOGS / "paper_trades.csv"
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row.get("entry_timestamp") or row.get("signal_timestamp") or ""
            if ts.startswith(day):
                rows.append(row)
    return rows


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(ET).strftime("%Y-%m-%d")
    replay = sequential_replay(day, pass_chase=True, pass_late=True)
    paper = paper_trades_for_day(day)

    paper_r = sum(float(r["gross_R"]) for r in paper if r.get("gross_R"))
    print(f"=== Paper vs Replay — {day} ===\n")
    print(f"Sequential replay: {replay.trades_taken} trades, {replay.wins}W/{replay.losses}L, {replay.total_gross_r:+.2f}R")
    print(f"Paper journal:     {len(paper)} trades, {paper_r:+.2f}R")

    if not paper:
        print("\nNo paper_trades.csv rows for this day (run --mode paper first).")
        print(f"Bar source: {'bars.csv (full OHLC)' if (LOGS / 'bars.csv').exists() else 'decisions WATCH (close-derived)'}")
        return 0

    drift = paper_r - replay.total_gross_r
    print(f"Drift (paper - replay): {drift:+.2f}R")
    if abs(drift) <= 2.0:
        print("Status: ALIGNED (within 2R)")
    else:
        print("Status: REVIEW — check DATA_MISSING, skipped signals, or slippage settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
