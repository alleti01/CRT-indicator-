#!/usr/bin/env python3
"""Phase76 checkpoint 02 — prefix / causality audit."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase76.python.causality import run_causality_audit, write_causality_report  # noqa: E402
from phase76.python.data_loader import load_nq_1m  # noqa: E402


def main() -> int:
    print("Loading 1m data...")
    df = load_nq_1m()
    print(f"  {len(df):,} bars — running prefix invariance audit (may take several minutes)...")
    report = run_causality_audit(df)
    path = write_causality_report(report)
    print(f"Verdict: {report['verdict']}")
    print(f"Report: {path}")
    return 0 if report["verdict"] == "CAUSALITY_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
