#!/usr/bin/env python3
"""Run retest structure-failure forensics on recovered BOS candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.recovered_retest_structure_forensics import run_retest_structure_forensics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="phase16/data/processed/nq_5m.csv")
    parser.add_argument("--output", default="phase16/results/recovered_retest_structure_forensics")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-26")
    args = parser.parse_args()

    config = FrozenConfig()
    data = load_ohlcv_csv(args.data, exchange_timezone=config.exchange_timezone)
    manifest = run_retest_structure_forensics(
        data,
        start=args.start,
        end=args.end,
        config=config,
        output=Path(args.output),
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
