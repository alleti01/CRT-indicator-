#!/usr/bin/env python3
"""Run the frozen Retest-gated event-level forensic trace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase16.continuous import forward_adjust_rolls, select_provider_rolls
from phase16.data_loader import load_ohlcv_csv
from phase16.resample import resample_ohlcv
from phase16.retest_gate_forensics import run_forensics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--start", default="2026-06-29")
    parser.add_argument("--end", default="2026-08-18")
    parser.add_argument("--output", default="phase16/results/retest_gate_forensics")
    parser.add_argument("--source-timezone")
    parser.add_argument(
        "--provider-roll",
        action="store_true",
        help="Use the provider instrument transitions and causal forward adjustment",
    )
    parser.add_argument(
        "--keep-incomplete-resamples",
        action="store_true",
        help="Match the validated parity preparation for the downloaded continuous file",
    )
    args = parser.parse_args()

    config = FrozenConfig()
    data = load_ohlcv_csv(
        args.data,
        source_timezone=args.source_timezone,
        exchange_timezone=config.exchange_timezone,
    )
    if args.provider_roll:
        data = forward_adjust_rolls(select_provider_rolls(data))
    data = resample_ohlcv(
        data,
        config.chart_minutes,
        require_complete=not args.keep_incomplete_resamples,
    )
    summary = run_forensics(
        data,
        start=args.start,
        end=args.end,
        output=Path(args.output),
        config=config,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
