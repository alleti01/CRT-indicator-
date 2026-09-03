#!/usr/bin/env python3
"""Add New York time columns to manual review CSVs (TV x-axis is usually NY)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
NY = "America/New_York"
CHI = "America/Chicago"


def _to_ny(series: pd.Series) -> pd.Series:
    t = pd.to_datetime(series, utc=False)
    if t.dt.tz is None:
        t = t.dt.tz_localize(CHI)
    return t.dt.tz_convert(NY)


def patch_csv(path: Path, time_cols: list[str]) -> None:
    if not path.exists():
        return
    df = pd.read_csv(path)
    for col in time_cols:
        if col in df.columns and df[col].notna().any():
            ny_col = col.replace("_time", "_time_ny") if col.endswith("_time") else col + "_ny"
            if ny_col not in df.columns:
                df[ny_col] = _to_ny(df[col]).astype(str)
    df.to_csv(path, index=False)
    print(f"Updated {path.name} (+ NY columns)")


def main():
    sample_path = ROOT / "phase72" / "manual_review" / "sample.csv"
    if sample_path.exists():
        df = pd.read_csv(sample_path)
        for src, dst in [
            ("entry_time", "entry_time_ny"),
            ("signal_time", "signal_time_ny"),
        ]:
            if src in df.columns:
                df[dst] = _to_ny(df[src]).dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        df["tv_timezone_note"] = "TradingView x-axis: use entry_time_ny / signal_time_ny"
        df.to_csv(sample_path, index=False)
        for copy in [
            ROOT / "phase72" / "manual_review" / "sample_jul_aug_2026.csv",
            ROOT / "phase72a" / "manual_review" / "sample_jul_aug_2026.csv",
        ]:
            if copy.parent.exists():
                df.to_csv(copy, index=False)

    e2e = ROOT / "phase72a" / "manual_review" / "end_to_end_review.csv"
    if e2e.exists():
        df = pd.read_csv(e2e)
        if "python_entry_time" in df.columns:
            df["python_entry_time_ny"] = _to_ny(df["python_entry_time"]).dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        if "python_signal_time" in df.columns:
            df["python_signal_time_ny"] = _to_ny(df["python_signal_time"]).dt.strftime("%Y-%m-%d %H:%M:%S %Z")
        df["tv_timezone_note"] = "Navigate TradingView using *_ny columns (America/New_York)"
        # reorder: put NY columns after Chicago for readability
        cols = list(df.columns)
        for c in ["python_signal_time_ny", "python_entry_time_ny"]:
            if c in cols:
                cols.remove(c)
        insert_at = cols.index("python_entry_time") + 1 if "python_entry_time" in cols else len(cols)
        for c in reversed(["python_entry_time_ny", "python_signal_time_ny"]):
            if c in df.columns:
                cols.insert(insert_at, c)
        df = df[[c for c in cols if c in df.columns]]
        df.to_csv(e2e, index=False)
        print(f"Updated end_to_end_review.csv")

    log = ROOT / "phase72" / "manual_review" / "manual_review_log_template.csv"
    patch_csv(log, ["entry_time", "signal_time"])


if __name__ == "__main__":
    main()
