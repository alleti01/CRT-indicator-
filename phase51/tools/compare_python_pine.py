#!/usr/bin/env python3
"""Compare Phase49 Python forward events vs Phase51 Pine forward log."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from phase51.config import PRICE_TOLERANCE, RESULTS_DIR, TIMEZONE

COLUMNS = [
    "signal_id",
    "timestamp",
    "python_phase44",
    "pine_phase44",
    "python_b1",
    "pine_b1",
    "python_direction",
    "pine_direction",
    "python_entry",
    "pine_entry",
    "python_stop",
    "pine_stop",
    "python_target",
    "pine_target",
    "status",
    "reason",
]


def _ts(val) -> pd.Timestamp | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    ts = pd.Timestamp(val)
    if ts.tzinfo is None:
        ts = ts.tz_localize(TIMEZONE)
    else:
        ts = ts.tz_convert(TIMEZONE)
    return ts


def _price_ok(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b):
        return False
    return abs(a - b) <= PRICE_TOLERANCE + 1e-9


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--python-forward",
        type=Path,
        default=Path("phase49/results/forward_validation/forward_signals.csv"),
    )
    parser.add_argument(
        "--pine-trades",
        type=Path,
        default=Path("phase51/forward/trades.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RESULTS_DIR / "python_pine_forward_parity.csv",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    py = pd.read_csv(args.python_forward) if args.python_forward.exists() else pd.DataFrame()
    pine = pd.read_csv(args.pine_trades) if args.pine_trades.exists() else pd.DataFrame()

    rows: list[dict] = []
    if py.empty or pine.empty:
        pd.DataFrame(columns=COLUMNS).to_csv(args.output, index=False)
        print(f"No overlapping data — wrote empty template: {args.output}")
        return 0

    py_filled = py.loc[py.get("filled", False).astype(bool)].copy() if "filled" in py.columns else py.copy()
    for _, pr in py_filled.iterrows():
        ts = _ts(pr.get("entry_time") or pr.get("b1_time"))
        match = pine.loc[pine["entry_time_ct"] == pr.get("entry_time")] if "entry_time_ct" in pine.columns else pd.DataFrame()
        if match.empty and ts is not None:
            pine_ts = pd.to_datetime(pine.get("entry_time_ct", pd.Series(dtype=str)), errors="coerce")
            if pine_ts.dt.tz is None and len(pine_ts.dropna()):
                pine_ts = pine_ts.dt.tz_localize(TIMEZONE, ambiguous="NaT", nonexistent="NaT")
            match = pine.loc[abs((pine_ts - ts).dt.total_seconds()) <= 60]

        if match.empty:
            rows.append(
                {
                    "signal_id": pr.get("signal_id", ""),
                    "timestamp": ts,
                    "python_direction": pr.get("direction"),
                    "python_entry": pr.get("entry_price"),
                    "status": "MISSING_PINE",
                    "reason": "no matching pine forward trade",
                }
            )
            continue

        pl = match.iloc[0]
        status = "MATCH"
        reason = ""
        if str(pr.get("direction", "")).upper() != str(pl.get("direction", "")).upper():
            status = "DIRECTION_MISMATCH"
            reason = "direction differs"
        elif not _price_ok(float(pr.get("entry_price", np.nan)), float(pl.get("entry_price", np.nan))):
            status = "ENTRY_MISMATCH"
            reason = f"entry delta > {PRICE_TOLERANCE}"
        rows.append(
            {
                "signal_id": pl.get("signal_id", pr.get("signal_id", "")),
                "timestamp": ts,
                "python_phase44": pr.get("phase44_time"),
                "pine_phase44": pl.get("phase44_time_ct"),
                "python_b1": pr.get("b1_time"),
                "pine_b1": pl.get("b1_time_ct"),
                "python_direction": pr.get("direction"),
                "pine_direction": pl.get("direction"),
                "python_entry": pr.get("entry_price"),
                "pine_entry": pl.get("entry_price"),
                "python_stop": pr.get("stop"),
                "pine_stop": pl.get("stop_price"),
                "python_target": pr.get("target"),
                "pine_target": pl.get("target_price"),
                "status": status,
                "reason": reason,
            }
        )

    pd.DataFrame(rows, columns=COLUMNS).to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
