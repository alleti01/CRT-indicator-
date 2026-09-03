#!/usr/bin/env python3
"""Run Phase 27 order-flow entry discovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase27.analyze import run_phase27
from phase27.config import DATA_RAW, RESULTS


def main() -> int:
    trades = DATA_RAW / "nq_trades_pilot_202401.csv"
    if not trades.exists():
        print("ERROR: pilot trades file missing; see data_cost_audit.md", file=sys.stderr)
        return 2
    manifest = run_phase27(trades_path=trades, output=RESULTS)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
