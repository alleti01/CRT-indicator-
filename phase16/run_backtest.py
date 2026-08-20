#!/usr/bin/env python3
"""Command-line runner for Phase 16 parity and OOS validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from phase16.backtest import run_backtest
    from phase16.config import FrozenConfig
    from phase16.continuous import (
        forward_adjust_rolls,
        select_explicit_rolls,
        select_provider_rolls,
        select_volume_rolls,
    )
    from phase16.data_loader import infer_bar_minutes, load_ohlcv_csv, normalize_ohlcv
    from phase16.reporting import write_oos_outputs, write_parity_outputs
    from phase16.resample import resample_ohlcv
    from phase16.validation import read_reference, require_parity_pass
else:
    from .backtest import run_backtest
    from .config import FrozenConfig
    from .continuous import (
        forward_adjust_rolls,
        select_explicit_rolls,
        select_provider_rolls,
        select_volume_rolls,
    )
    from .data_loader import infer_bar_minutes, load_ohlcv_csv, normalize_ohlcv
    from .reporting import write_oos_outputs, write_parity_outputs
    from .resample import resample_ohlcv
    from .validation import read_reference, require_parity_pass


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Frozen CRT Phase 16 backtester")
    command.add_argument("--data", required=True, help="Prepared continuous or contract OHLCV CSV")
    command.add_argument("--start", help="Inclusive exchange-local YYYY-MM-DD")
    command.add_argument("--end", help="Inclusive exchange-local YYYY-MM-DD")
    command.add_argument("--mode", choices=["parity", "oos"], required=True)
    command.add_argument("--output", default="results", help="Output directory")
    command.add_argument("--source-timezone", help="Timezone for naive CSV timestamps")
    command.add_argument("--debug-events", action="store_true")
    command.add_argument("--reference", help="TradingView metrics CSV for parity")
    command.add_argument(
        "--breakdown-reference",
        help="TradingView direction/regime/session/score/date-third CSV",
    )
    command.add_argument("--parity-report", help="Passing parity_summary.csv required for OOS")
    command.add_argument(
        "--contracts",
        choices=["prepared", "provider-roll", "volume", "explicit"],
        default="prepared",
        help="Continuous input or individual-contract construction method",
    )
    command.add_argument("--contract-order", help="Chronological comma-separated symbols")
    command.add_argument("--roll-schedule", help="CSV: roll_timestamp,new_contract")
    command.add_argument("--initial-contract", help="First active contract for explicit rolls")
    command.add_argument("--roll-confirm-sessions", type=int, default=1)
    command.add_argument(
        "--keep-incomplete-resamples",
        action="store_true",
        help="Keep 5m bars formed from fewer than five 1m records",
    )
    return command


def _prepare_data(args: argparse.Namespace, config: FrozenConfig) -> pd.DataFrame:
    data = load_ohlcv_csv(
        args.data,
        source_timezone=args.source_timezone,
        exchange_timezone=config.exchange_timezone,
    )
    if args.contracts == "volume":
        if not args.contract_order:
            raise ValueError("--contract-order is required for volume rolls")
        order = [symbol.strip() for symbol in args.contract_order.split(",") if symbol.strip()]
        data = select_volume_rolls(
            data, order, confirm_sessions=args.roll_confirm_sessions
        )
        data = forward_adjust_rolls(data)
    elif args.contracts == "provider-roll":
        data = select_provider_rolls(data)
        data = forward_adjust_rolls(data)
    elif args.contracts == "explicit":
        if not args.roll_schedule or not args.initial_contract:
            raise ValueError(
                "--roll-schedule and --initial-contract are required for explicit rolls"
            )
        schedule = pd.read_csv(args.roll_schedule)
        data = select_explicit_rolls(data, args.initial_contract, schedule)
        data = forward_adjust_rolls(data)

    minutes = infer_bar_minutes(data)
    if minutes == 1:
        data = resample_ohlcv(
            data,
            config.chart_minutes,
            require_complete=not args.keep_incomplete_resamples,
        )
    elif minutes != config.chart_minutes:
        raise ValueError(
            f"input appears to be {minutes}-minute data; expected 1m or {config.chart_minutes}m"
        )
    return data


def _ensure_non_overlapping_oos(start: str, end: str, config: FrozenConfig) -> None:
    requested_start = pd.Timestamp(start).date()
    requested_end = pd.Timestamp(end).date()
    development_start = pd.Timestamp(config.development_start).date()
    development_end = pd.Timestamp(config.development_end).date()
    overlaps = requested_start <= development_end and requested_end >= development_start
    if overlaps:
        raise RuntimeError(
            "OOS is blocked: requested dates overlap the development parity window"
        )


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    config = FrozenConfig()
    if args.mode == "parity":
        start = args.start or config.development_start
        end = args.end or config.development_end
    else:
        if not args.start or not args.end:
            raise ValueError("OOS mode requires --start and --end")
        if not args.parity_report:
            raise RuntimeError("OOS is blocked: provide --parity-report from a passing parity run")
        require_parity_pass(args.parity_report)
        _ensure_non_overlapping_oos(args.start, args.end, config)
        start, end = args.start, args.end

    data = _prepare_data(args, config)
    result = run_backtest(
        data,
        start=start,
        end=end,
        config=config,
        debug_events=args.debug_events,
    )
    output = Path(args.output)
    if args.mode == "parity":
        reference = read_reference(args.reference) if args.reference else None
        breakdown_reference = (
            pd.read_csv(args.breakdown_reference) if args.breakdown_reference else None
        )
        status = write_parity_outputs(
            result,
            output,
            config,
            reference=reference,
            breakdown_reference=breakdown_reference,
            debug_events=args.debug_events,
        )
        print(f"Coverage: {result.coverage}")
        print(f"Parity status: {status}")
    else:
        if result.coverage != "FULL DATA":
            raise RuntimeError(
                "OOS is blocked: loaded data does not cover the complete requested window"
            )
        write_oos_outputs(
            result, output, config, debug_events=args.debug_events
        )
        print(f"Coverage: {result.coverage}")
        print("OOS status: COMPLETE (frozen Retest; no optimization performed)")
    for key, value in result.diagnostics.items():
        print(f"{key}: {value}")
    print(f"Results: {output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
