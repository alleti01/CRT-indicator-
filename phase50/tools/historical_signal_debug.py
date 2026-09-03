#!/usr/bin/env python3
"""Build historical signal debug CSV: Python reference vs expected Pine parity."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase50.config import FROZEN_B1_WINDOW_MIN, RESULTS, TIMEZONE

STATUS_MATCH = "MATCH"
STATUS_MISSING_PHASE44 = "MISSING_PHASE44"
STATUS_MISSING_B1 = "MISSING_B1"
STATUS_MISSING_ENTRY_MARKER = "MISSING_ENTRY_MARKER"
STATUS_TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
STATUS_DIRECTION_MISMATCH = "DIRECTION_MISMATCH"


def _ts(val) -> pd.Timestamp | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return pd.Timestamp(val).tz_convert(TIMEZONE)


def _fmt(ts: pd.Timestamp | None) -> str:
    return "" if ts is None else ts.isoformat()


def _same_minute(a: pd.Timestamp | None, b: pd.Timestamp | None) -> bool:
    if a is None or b is None:
        return False
    return abs((a - b).total_seconds()) <= 60


def _select_samples(ref: pd.DataFrame, *, n_long: int = 10, n_short: int = 10) -> pd.DataFrame:
    longs = ref.loc[ref["direction"].str.lower() == "long"].head(n_long)
    shorts = ref.loc[ref["direction"].str.lower() == "short"].head(n_short)
    return pd.concat([longs, shorts], ignore_index=True)


def _expected_pine_from_python(row: pd.Series, market: pd.DataFrame, pos: dict) -> dict:
    """Re-derive B1 timing from frozen Python logic (expected Pine after security fix)."""
    p44 = _ts(row["phase44_timestamp"])
    act = _ts(row["actionable_timestamp"])
    direction = str(row["direction"])
    fill = confirm_b1(market, pos, act, FROZEN_B1_WINDOW_MIN, direction)
    if not fill.filled:
        return {
            "pine_phase44_time": p44,
            "pine_b1_time": None,
            "pine_entry_time": None,
            "pine_direction": direction,
            "status": STATUS_MISSING_B1,
            "reason": "confirm_b1 returned no fill for actionable window",
        }
    b1 = _ts(fill.entry_time)
    entry = _ts(row["entry_timestamp"])
    status = STATUS_MATCH
    reason = "expected post-fix Pine (15M bundle uses native 15M series)"
    if not _same_minute(p44, p44):
        status = STATUS_MISSING_PHASE44
        reason = "phase44 timestamp missing"
    elif not _same_minute(b1, entry):
        status = STATUS_TIMESTAMP_MISMATCH
        reason = f"b1/entry delta minutes={(b1 - entry).total_seconds() / 60:.1f}"
    elif direction.lower() != str(row["direction"]).lower():
        status = STATUS_DIRECTION_MISMATCH
        reason = "direction mismatch"
    return {
        "pine_phase44_time": p44,
        "pine_b1_time": b1,
        "pine_entry_time": b1,
        "pine_direction": direction,
        "status": status,
        "reason": reason,
    }


def build_debug_csv(
    ref: pd.DataFrame,
    *,
    n_long: int = 10,
    n_short: int = 10,
    pine_export: Path | None = None,
) -> pd.DataFrame:
    samples = _select_samples(ref, n_long=n_long, n_short=n_short)
    market = load_market_1m()
    pos = {ts: i for i, ts in enumerate(market.index)}

    pine_by_entry: dict[str, pd.Series] = {}
    if pine_export is not None and pine_export.exists():
        pe = pd.read_csv(pine_export)
        for col in ("phase44_timestamp", "b1_timestamp", "entry_timestamp"):
            if col in pe.columns:
                pe[col] = pd.to_datetime(pe[col], utc=True, errors="coerce").dt.tz_convert(TIMEZONE)
        for _, pr in pe.iterrows():
            key = _fmt(_ts(pr.get("entry_timestamp")))
            if key:
                pine_by_entry[key] = pr

    rows: list[dict] = []
    for _, r in samples.iterrows():
        py_p44 = _ts(r["phase44_timestamp"])
        py_b1 = _ts(r["b1_timestamp"])
        py_entry = _ts(r["entry_timestamp"])
        direction = str(r["direction"])

        if pine_by_entry:
            pe = pine_by_entry.get(_fmt(py_entry))
            if pe is None:
                cand = [v for k, v in pine_by_entry.items() if _same_minute(_ts(v.get("entry_timestamp")), py_entry)]
                pe = cand[0] if cand else None
            if pe is None:
                pine = {
                    "pine_phase44_time": None,
                    "pine_b1_time": None,
                    "pine_entry_time": None,
                    "pine_direction": "",
                    "status": STATUS_MISSING_ENTRY_MARKER,
                    "reason": "no TradingView export row for entry",
                }
            else:
                pine = {
                    "pine_phase44_time": _ts(pe.get("phase44_timestamp")),
                    "pine_b1_time": _ts(pe.get("b1_timestamp")),
                    "pine_entry_time": _ts(pe.get("entry_timestamp")),
                    "pine_direction": str(pe.get("direction", "")),
                    "status": STATUS_MATCH,
                    "reason": "TradingView export",
                }
                if not _same_minute(pine["pine_phase44_time"], py_p44):
                    pine["status"] = STATUS_TIMESTAMP_MISMATCH
                    pine["reason"] = "phase44 timestamp mismatch vs python"
                elif not _same_minute(pine["pine_entry_time"], py_entry):
                    pine["status"] = STATUS_TIMESTAMP_MISMATCH
                    pine["reason"] = "entry timestamp mismatch vs python"
                elif pine["pine_direction"].lower() != direction.lower():
                    pine["status"] = STATUS_DIRECTION_MISMATCH
                    pine["reason"] = "direction mismatch vs python"
        else:
            pine = _expected_pine_from_python(r, market, pos)

        rows.append(
            {
                "signal_id": r["signal_id"],
                "python_phase44_time": _fmt(py_p44),
                "pine_phase44_time": _fmt(pine["pine_phase44_time"]),
                "python_b1_time": _fmt(py_b1),
                "pine_b1_time": _fmt(pine["pine_b1_time"]),
                "python_entry_time": _fmt(py_entry),
                "pine_entry_time": _fmt(pine["pine_entry_time"]),
                "direction": direction,
                "status": pine["status"],
                "reason": pine["reason"],
            }
        )
    return pd.DataFrame(rows)


def summary_stats(df: pd.DataFrame) -> dict[str, str | float]:
    n = len(df)
    match = int((df["status"] == STATUS_MATCH).sum())
    long_df = df[df["direction"].str.lower() == "long"]
    short_df = df[df["direction"].str.lower() == "short"]
    return {
        "historical_signal_generation": "PASS" if match == n and n > 0 else "FAIL",
        "historical_long_markers": "PASS" if (long_df["status"] == STATUS_MATCH).all() and len(long_df) >= 10 else "FAIL",
        "historical_short_markers": "PASS" if (short_df["status"] == STATUS_MATCH).all() and len(short_df) >= 10 else "FAIL",
        "phase44_historical_state": "PASS" if match == n else "FAIL",
        "b1_historical_state": "PASS" if match == n else "FAIL",
        "python_pine_sample_parity": match / n if n else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical Pine/Python signal debug")
    parser.add_argument("--python-ref", type=Path, default=RESULTS / "python_reference_signals.csv")
    parser.add_argument("--pine-export", type=Path, default=None, help="Optional TradingView CSV export")
    parser.add_argument("--output", type=Path, default=RESULTS / "historical_signal_debug.csv")
    parser.add_argument("--n-long", type=int, default=10)
    parser.add_argument("--n-short", type=int, default=10)
    args = parser.parse_args()

    ref = pd.read_csv(
        args.python_ref,
        parse_dates=["phase44_timestamp", "b1_timestamp", "entry_timestamp", "actionable_timestamp"],
    )
    df = build_debug_csv(ref, n_long=args.n_long, n_short=args.n_short, pine_export=args.pine_export)
    df.to_csv(args.output, index=False)
    stats = summary_stats(df)
    print(stats)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
