#!/usr/bin/env python3
"""Prepare and validate Databento continuous NQ data for frozen Phase 16 OOS.

This module is data infrastructure only. It does not import or alter the
strategy, setup, funnel, or trade engines.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

if __package__ in {None, ""}:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from phase16.continuous import forward_adjust_rolls, select_provider_rolls
    from phase16.data_loader import normalize_ohlcv, save_ohlcv
    from phase16.resample import resample_ohlcv
else:
    from .continuous import forward_adjust_rolls, select_provider_rolls
    from .data_loader import normalize_ohlcv, save_ohlcv
    from .resample import resample_ohlcv


EXCHANGE_TIMEZONE = "America/Chicago"


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Build a causally adjusted 5m NQ continuous dataset"
    )
    command.add_argument("--input", action="append", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--validation-dir", required=True)
    command.add_argument("--oos-start", required=True)
    command.add_argument("--oos-end", required=True)
    command.add_argument("--development-start", required=True)
    return command


def _gap_kind(previous: pd.Timestamp, current: pd.Timestamp, minutes: int) -> str:
    if previous.weekday() == 4 and current.weekday() == 6:
        return "weekend_close"
    if (
        previous.date() == current.date()
        and previous.hour == 15
        and previous.minute == 59
        and current.hour == 17
        and current.minute == 0
    ):
        return "daily_maintenance"
    if minutes >= 60:
        return "holiday_or_scheduled_closure"
    return "potential_missing_intraday"


def _gap_report(index: pd.DatetimeIndex, expected_minutes: int) -> pd.DataFrame:
    columns = ["previous", "current", "gap_minutes", "missing_bars", "classification"]
    if len(index) < 2:
        return pd.DataFrame(columns=columns)
    series = index.to_series(index=range(len(index)))
    differences = series.diff().dt.total_seconds().div(60)
    rows = []
    for position in differences[differences > expected_minutes].index:
        previous = pd.Timestamp(series.iloc[position - 1])
        current = pd.Timestamp(series.iloc[position])
        minutes = int(differences.iloc[position])
        missing = max(0, minutes // expected_minutes - 1)
        rows.append(
            {
                "previous": previous,
                "current": current,
                "gap_minutes": minutes,
                "missing_bars": missing,
                "classification": _gap_kind(previous, current, minutes),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _invalid_ohlc(frame: pd.DataFrame) -> int:
    high_floor = frame[["open", "close", "low"]].max(axis=1)
    low_ceiling = frame[["open", "close", "high"]].min(axis=1)
    invalid = (frame["high"] < high_floor) | (frame["low"] > low_ceiling)
    invalid |= frame["high"] < frame["low"]
    return int(invalid.sum())


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    input_paths = [Path(path) for path in args.input]
    frames = [pd.read_csv(path) for path in input_paths]
    downloaded_rows = sum(len(frame) for frame in frames)
    raw_combined = pd.concat(frames, ignore_index=True)

    identity = ["timestamp", "instrument_id"]
    duplicate_download_rows = int(raw_combined.duplicated(identity).sum())
    normalized = normalize_ohlcv(
        raw_combined,
        source_timezone="UTC",
        exchange_timezone=EXCHANGE_TIMEZONE,
    )
    provider = select_provider_rolls(normalized)

    transition_mask = provider["contract"].ne(provider["contract"].shift())
    transition_positions = [
        position
        for position, changed in enumerate(transition_mask.to_numpy())
        if changed and position > 0
    ]
    roll_rows = []
    for position in transition_positions:
        previous = provider.iloc[position - 1]
        current = provider.iloc[position]
        roll_rows.append(
            {
                "roll_timestamp": provider.index[position],
                "from_instrument": str(previous["contract"]),
                "to_instrument": str(current["contract"]),
                "raw_gap_points": float(current["open"] - previous["close"]),
            }
        )

    adjusted = forward_adjust_rolls(provider)
    for row, position in zip(roll_rows, transition_positions):
        row["adjustment_points"] = float(adjusted.iloc[position]["roll_adjustment"])
        row["adjusted_gap_points"] = float(
            adjusted.iloc[position]["open"] - adjusted.iloc[position - 1]["close"]
        )

    # Phase 16 parity was validated with --keep-incomplete-resamples. Databento
    # OHLCV omits a minute when there is no record, while TradingView still
    # represents the enclosing 5m interval. Preserve that validated behavior:
    # aggregate every non-empty, clock-aligned 5m bucket and keep the strict
    # version only to quantify affected buckets in the validation report.
    final_5m = resample_ohlcv(adjusted, 5, require_complete=False)
    strict_5m = resample_ohlcv(adjusted, 5, require_complete=True)

    oos_start = pd.Timestamp(args.oos_start, tz=EXCHANGE_TIMEZONE)
    oos_end_exclusive = pd.Timestamp(args.oos_end, tz=EXCHANGE_TIMEZONE) + pd.Timedelta(
        1, unit="D"
    )
    development_start = pd.Timestamp(args.development_start, tz=EXCHANGE_TIMEZONE)
    if oos_end_exclusive > development_start:
        raise RuntimeError("OOS preparation overlaps the development window")
    if not final_5m.index.is_monotonic_increasing:
        raise RuntimeError("processed timestamps are not sorted")
    duplicate_5m = int(final_5m.index.duplicated().sum())
    if duplicate_5m:
        raise RuntimeError(f"processed data contains {duplicate_5m} duplicate timestamps")
    invalid_5m = _invalid_ohlc(final_5m)
    if invalid_5m:
        raise RuntimeError(f"processed data contains {invalid_5m} invalid OHLC rows")
    if final_5m.index.max() >= development_start:
        raise RuntimeError("processed data includes a development-window timestamp")

    oos_mask = (final_5m.index >= oos_start) & (final_5m.index < oos_end_exclusive)
    oos_bars = final_5m.loc[oos_mask]
    if oos_bars.empty:
        raise RuntimeError("processed data contains no OOS bars")

    validation = Path(args.validation_dir)
    validation.mkdir(parents=True, exist_ok=True)
    raw_gaps = _gap_report(normalized.index, 1)
    gaps_5m = _gap_report(oos_bars.index, 5)
    raw_gaps.to_csv(validation / "raw_1m_gap_report.csv", index=False)
    gaps_5m.to_csv(validation / "processed_5m_gap_report.csv", index=False)
    pd.DataFrame(roll_rows).to_csv(validation / "roll_report.csv", index=False)

    # Store UTC timestamps in CSV so mixed CST/CDT offsets parse consistently;
    # the loader always converts them back to America/Chicago before evaluation.
    output_frame = final_5m.copy()
    output_frame.index = output_frame.index.tz_convert("UTC")
    save_ohlcv(output_frame, args.output)

    potential_raw = raw_gaps.loc[
        raw_gaps["classification"].eq("potential_missing_intraday")
    ]
    potential_5m = gaps_5m.loc[
        gaps_5m["classification"].eq("potential_missing_intraday")
    ]
    report = {
        "input_files": [str(path) for path in input_paths],
        "downloaded_rows": downloaded_rows,
        "duplicate_download_rows": duplicate_download_rows,
        "normalized_unique_1m_rows": len(normalized),
        "first_1m_timestamp": str(normalized.index.min()),
        "last_1m_timestamp": str(normalized.index.max()),
        "timezone": str(normalized.index.tz),
        "roll_count": len(roll_rows),
        "maximum_absolute_adjusted_roll_gap_points": max(
            (abs(float(row["adjusted_gap_points"])) for row in roll_rows), default=0.0
        ),
        "final_5m_rows": len(final_5m),
        "strict_5m_rows": len(strict_5m),
        "incomplete_5m_groups_retained": len(final_5m) - len(strict_5m),
        "oos_5m_rows": len(oos_bars),
        "first_oos_5m_timestamp": str(oos_bars.index.min()),
        "last_oos_5m_timestamp": str(oos_bars.index.max()),
        "duplicate_5m_rows": duplicate_5m,
        "invalid_ohlc_rows": invalid_5m,
        "raw_gap_count": len(raw_gaps),
        "potential_missing_raw_1m_gaps": len(potential_raw),
        "processed_gap_count": len(gaps_5m),
        "potential_missing_5m_gaps": len(potential_5m),
        "development_overlap_rows": int((final_5m.index >= development_start).sum()),
        "coverage_left": bool(final_5m.index.min() <= oos_start),
        "coverage_right": bool(
            final_5m.index.max() + pd.Timedelta(5, unit="min") >= oos_end_exclusive
        ),
    }
    (validation / "data_validation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Processed data: {Path(args.output).resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(2)
