#!/usr/bin/env python3
"""Run the preregistered H1/H2/H3 quality-filter study."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.backtest import run_backtest
from phase16.config import FrozenConfig
from phase16.continuous import forward_adjust_rolls, select_provider_rolls
from phase16.data_loader import load_ohlcv_csv
from phase16.focused_hypothesis_testing import run_focused_tests, verify_reference_baseline
from phase16.resample import resample_ohlcv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-data", default="phase16/data/nq_continuous_1m_raw.csv")
    parser.add_argument("--development-data", default="phase16/data/processed/nq_5m.csv")
    parser.add_argument("--output", default="phase16/results/focused_hypothesis_testing")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-06-26")
    args = parser.parse_args()

    config = FrozenConfig()
    reference_data = load_ohlcv_csv(args.reference_data, exchange_timezone=config.exchange_timezone)
    reference_data = forward_adjust_rolls(select_provider_rolls(reference_data))
    reference_data = resample_ohlcv(reference_data, config.chart_minutes, require_complete=False)
    reference_result = run_backtest(
        reference_data,
        start=config.development_start,
        end=config.development_end,
        config=config,
    )
    reference_confirm = reference_result.trades.loc[reference_result.trades.model == "Confirm"].copy()
    reference_metrics = verify_reference_baseline(reference_confirm)
    print("REFERENCE BASELINE: PASS")

    development_data = load_ohlcv_csv(args.development_data, exchange_timezone=config.exchange_timezone)
    development_result = run_backtest(
        development_data,
        start=args.start,
        end=args.end,
        config=config,
    )
    if development_result.coverage != "FULL DATA":
        raise RuntimeError("larger development data does not fully cover the requested range")
    development_confirm = development_result.trades.loc[development_result.trades.model == "Confirm"].copy()
    manifest = run_focused_tests(
        large_frame=development_data,
        large_confirm_trades=development_confirm,
        reference_metrics=reference_metrics,
        output=Path(args.output),
        config=config,
        start=args.start,
        end=args.end,
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

