#!/usr/bin/env python3
"""Compare Pine-exported events against Python reference signals."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from phase50.config import PRICE_TOLERANCE, RESULTS, TIMEZONE


MATCH = "MATCH"
MISSING_IN_PINE = "MISSING_IN_PINE"
EXTRA_IN_PINE = "EXTRA_IN_PINE"
TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
CLASS_MISMATCH = "CLASS_MISMATCH"
SETUP_MISMATCH = "SETUP_MISMATCH"
ENTRY_MISMATCH = "ENTRY_MISMATCH"
STOP_MISMATCH = "STOP_MISMATCH"
TARGET_MISMATCH = "TARGET_MISMATCH"
EXIT_MISMATCH = "EXIT_MISMATCH"


def _norm_ts(val) -> pd.Timestamp | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return pd.Timestamp(val).tz_convert(TIMEZONE)


def _price_ok(a: float, b: float, tol: float = PRICE_TOLERANCE) -> bool:
    if not np.isfinite(a) or not np.isfinite(b):
        return False
    return abs(a - b) <= tol + 1e-9


def load_pine_export(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("phase44_timestamp", "b1_timestamp", "entry_timestamp", "exit_timestamp"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce").dt.tz_convert(TIMEZONE)
    return df


def _row_val(row, key: str, default=""):
    if isinstance(row, pd.Series):
        return row.get(key, default)
    return getattr(row, key, default)


def compare_events(python_ref: pd.DataFrame, pine: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    pine_by_entry: dict[str, pd.Series] = {}
    if not pine.empty and "entry_timestamp" in pine.columns:
        for _, pr in pine.iterrows():
            pine_by_entry[str(_norm_ts(pr["entry_timestamp"]))] = pr
    used_pine: set[str] = set()

    for r in python_ref.itertuples(index=False):
        key = str(_norm_ts(r.entry_timestamp))
        p = pine_by_entry.get(key)
        if p is None:
            candidates = pine.loc[
                (pd.to_datetime(pine["entry_timestamp"]).dt.tz_convert(TIMEZONE) - _norm_ts(r.entry_timestamp)).abs()
                <= pd.Timedelta(minutes=1)
            ] if not pine.empty and "entry_timestamp" in pine.columns else pd.DataFrame()
            p = candidates.iloc[0] if not candidates.empty else None

        if p is None:
            rows.append({"signal_id": r.signal_id, "status": MISSING_IN_PINE, "detail": "no pine entry match"})
            continue

        used_pine.add(str(_norm_ts(_row_val(p, "entry_timestamp"))))
        status = MATCH
        details: list[str] = []

        if str(_row_val(p, "direction")).lower() != str(r.direction).lower():
            status, details = DIRECTION_MISMATCH, details + ["direction"]

        if str(_row_val(p, "phase44_class")) != str(r.phase44_class):
            status, details = CLASS_MISMATCH if status == MATCH else status, details + ["class"]

        if str(_row_val(p, "setup_type")) != str(r.setup_type):
            status, details = SETUP_MISMATCH if status == MATCH else status, details + ["setup"]

        p_entry = float(_row_val(p, "entry_price", np.nan))
        if not _price_ok(p_entry, float(r.entry_price)):
            status, details = ENTRY_MISMATCH if status == MATCH else status, details + ["entry_price"]

        p_stop = float(_row_val(p, "stop", np.nan))
        if not _price_ok(p_stop, float(r.stop)):
            status, details = STOP_MISMATCH if status == MATCH else status, details + ["stop"]

        p_target = float(_row_val(p, "target", np.nan))
        if not _price_ok(p_target, float(r.target)):
            status, details = TARGET_MISMATCH if status == MATCH else status, details + ["target"]

        p_exit = str(_row_val(p, "exit_type", ""))
        if p_exit and str(r.exit_type) and p_exit != str(r.exit_type):
            status, details = EXIT_MISMATCH if status == MATCH else status, details + ["exit_type"]

        rows.append({"signal_id": r.signal_id, "status": status, "detail": ",".join(details) if details else ""})

    for _, p in pine.iterrows():
        key = str(_norm_ts(p.get("entry_timestamp")))
        if key not in used_pine:
            rows.append({"signal_id": p.get("signal_id", ""), "status": EXTRA_IN_PINE, "detail": key})

    return pd.DataFrame(rows)


def parity_summary(comparison: pd.DataFrame) -> dict:
    n = len(comparison)
    if n == 0:
        return {k: 0.0 for k in ("phase44", "b1", "entry", "direction", "stop", "target", "exit", "full_trade")}
    match = comparison.loc[comparison["status"] == MATCH]
    return {
        "total_compared": n,
        "matches": len(match),
        "mismatches": n - len(match),
        "full_trade_parity_rate": len(match) / n,
        "missing_in_pine": int((comparison["status"] == MISSING_IN_PINE).sum()),
        "extra_in_pine": int((comparison["status"] == EXTRA_IN_PINE).sum()),
        "logic_mismatches": int(comparison["status"].isin(
            [DIRECTION_MISMATCH, CLASS_MISMATCH, SETUP_MISMATCH, ENTRY_MISMATCH, STOP_MISMATCH, TARGET_MISMATCH, EXIT_MISMATCH]
        ).sum()),
        "timestamp_mismatches": int((comparison["status"] == TIMESTAMP_MISMATCH).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare Pine vs Python reference signals")
    parser.add_argument("--python-ref", type=Path, default=RESULTS / "python_reference_signals.csv")
    parser.add_argument("--pine-export", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=RESULTS / "full_parity_results.csv")
    args = parser.parse_args()

    py = pd.read_csv(args.python_ref, parse_dates=["phase44_timestamp", "b1_timestamp", "entry_timestamp", "exit_timestamp"])
    pine = load_pine_export(args.pine_export)
    cmp_df = compare_events(py, pine)
    cmp_df.to_csv(args.output, index=False)
    summary = parity_summary(cmp_df)
    pd.DataFrame([summary]).to_csv(RESULTS / "parity_summary.csv", index=False)
    print(summary)


if __name__ == "__main__":
    main()
