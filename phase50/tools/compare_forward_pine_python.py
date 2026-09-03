#!/usr/bin/env python3
"""Compare Phase49 forward Python events vs TradingView Pine export."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from phase50.config import PRICE_TOLERANCE, RESULTS, TIMEZONE

STATUS_MATCH = "MATCH"
STATUS_PENDING = "PENDING"
STATUS_MISSING_PINE = "MISSING_PINE"
STATUS_MISSING_PYTHON = "MISSING_PYTHON"
STATUS_DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
STATUS_TIMESTAMP_MISMATCH = "TIMESTAMP_MISMATCH"
STATUS_ENTRY_MISMATCH = "ENTRY_MISMATCH"
STATUS_STOP_MISMATCH = "STOP_MISMATCH"
STATUS_TARGET_MISMATCH = "TARGET_MISMATCH"

COLUMNS = [
    "timestamp",
    "python_phase44",
    "pine_phase44",
    "python_b1",
    "pine_b1",
    "python_entry",
    "pine_entry",
    "direction",
    "entry_price_python",
    "entry_price_pine",
    "stop_python",
    "stop_pine",
    "target_python",
    "target_pine",
    "status",
]


def _ts(val) -> pd.Timestamp | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    return pd.Timestamp(val).tz_convert(TIMEZONE)


def _same_minute(a: pd.Timestamp | None, b: pd.Timestamp | None) -> bool:
    if a is None or b is None:
        return False
    return abs((a - b).total_seconds()) <= 60


def _price_ok(a: float, b: float) -> bool:
    if not np.isfinite(a) or not np.isfinite(b):
        return False
    return abs(a - b) <= PRICE_TOLERANCE + 1e-9


def load_python_forward(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size < 80:
        return pd.DataFrame()
    df = pd.read_csv(path)
    rename = {
        "phase44_time": "python_phase44",
        "b1_time": "python_b1",
        "entry_time": "python_entry",
        "entry_price": "entry_price_python",
        "stop": "stop_python",
        "target": "target_python",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    filled = df.loc[df.get("filled", df.get("b1_confirmed", False)).astype(bool)].copy()
    if filled.empty:
        return filled
    for col in ("python_phase44", "python_b1", "python_entry"):
        if col.replace("python_", "") + "_time" in df.columns and col not in filled.columns:
            filled[col] = filled[col.replace("python_", "") + "_time"]
    for col in ("python_phase44", "python_b1", "python_entry"):
        if col in filled.columns:
            filled[col] = pd.to_datetime(filled[col], utc=True, errors="coerce").dt.tz_convert(TIMEZONE)
    filled["timestamp"] = filled.get("python_entry", filled.index)
    return filled


def load_pine_export(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    colmap = {
        "phase44_timestamp": "pine_phase44",
        "b1_timestamp": "pine_b1",
        "entry_timestamp": "pine_entry",
        "entry_price": "entry_price_pine",
        "stop": "stop_pine",
        "target": "target_pine",
    }
    df = df.rename(columns={k: v for k, v in colmap.items() if k in df.columns})
    for col in ("pine_phase44", "pine_b1", "pine_entry"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True, errors="coerce").dt.tz_convert(TIMEZONE)
    df["timestamp"] = df.get("pine_entry", pd.NaT)
    return df


def compare_forward(py: pd.DataFrame, pine: pd.DataFrame) -> pd.DataFrame:
    if py.empty and pine.empty:
        return pd.DataFrame(columns=COLUMNS)

    rows: list[dict] = []
    pine_by_entry: dict[str, pd.Series] = {}
    for _, pr in pine.iterrows():
        key = str(_ts(pr.get("pine_entry")))
        if key and key != "None":
            pine_by_entry[key] = pr
    used: set[str] = set()

    for _, r in py.iterrows():
        entry = _ts(r.get("python_entry"))
        key = str(entry)
        p = pine_by_entry.get(key)
        if p is None and not pine.empty:
            cands = pine.loc[
                (pd.to_datetime(pine["pine_entry"]).dt.tz_convert(TIMEZONE) - entry).abs() <= pd.Timedelta(minutes=1)
            ] if "pine_entry" in pine.columns else pd.DataFrame()
            p = cands.iloc[0] if not cands.empty else None

        row = {
            "timestamp": entry,
            "python_phase44": _ts(r.get("python_phase44")),
            "pine_phase44": _ts(p.get("pine_phase44")) if p is not None else None,
            "python_b1": _ts(r.get("python_b1")),
            "pine_b1": _ts(p.get("pine_b1")) if p is not None else None,
            "python_entry": entry,
            "pine_entry": _ts(p.get("pine_entry")) if p is not None else None,
            "direction": r.get("direction", ""),
            "entry_price_python": float(r.get("entry_price_python", r.get("entry_price", np.nan))),
            "entry_price_pine": float(p.get("entry_price_pine", np.nan)) if p is not None else np.nan,
            "stop_python": float(r.get("stop_python", r.get("stop", np.nan))),
            "stop_pine": float(p.get("stop_pine", np.nan)) if p is not None else np.nan,
            "target_python": float(r.get("target_python", r.get("target", np.nan))),
            "target_pine": float(p.get("target_pine", np.nan)) if p is not None else np.nan,
            "status": STATUS_MISSING_PINE if p is None else STATUS_MATCH,
        }
        if p is not None:
            used.add(str(_ts(p.get("pine_entry"))))
            if str(p.get("direction", "")).lower() != str(r.get("direction", "")).lower():
                row["status"] = STATUS_DIRECTION_MISMATCH
            elif not _same_minute(row["python_b1"], row["pine_b1"]):
                row["status"] = STATUS_TIMESTAMP_MISMATCH
            elif not _same_minute(row["python_entry"], row["pine_entry"]):
                row["status"] = STATUS_TIMESTAMP_MISMATCH
            elif not _price_ok(row["entry_price_python"], row["entry_price_pine"]):
                row["status"] = STATUS_ENTRY_MISMATCH
            elif not _price_ok(row["stop_python"], row["stop_pine"]):
                row["status"] = STATUS_STOP_MISMATCH
            elif not _price_ok(row["target_python"], row["target_pine"]):
                row["status"] = STATUS_TARGET_MISMATCH
        rows.append(row)

    for _, p in pine.iterrows():
        key = str(_ts(p.get("pine_entry")))
        if key not in used and key != "None":
            rows.append(
                {
                    "timestamp": _ts(p.get("pine_entry")),
                    "python_phase44": None,
                    "pine_phase44": _ts(p.get("pine_phase44")),
                    "python_b1": None,
                    "pine_b1": _ts(p.get("pine_b1")),
                    "python_entry": None,
                    "pine_entry": _ts(p.get("pine_entry")),
                    "direction": p.get("direction", ""),
                    "entry_price_python": np.nan,
                    "entry_price_pine": float(p.get("entry_price_pine", np.nan)),
                    "stop_python": np.nan,
                    "stop_pine": float(p.get("stop_pine", np.nan)),
                    "target_python": np.nan,
                    "target_pine": float(p.get("target_pine", np.nan)),
                    "status": STATUS_MISSING_PYTHON,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=COLUMNS)
    return out[COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Forward Phase49 Python vs Pine comparison")
    parser.add_argument(
        "--python-forward",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "phase49"
        / "results"
        / "forward_validation"
        / "forward_signals.csv",
    )
    parser.add_argument("--pine-export", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=RESULTS / "forward_pine_python_comparison.csv")
    args = parser.parse_args()

    py = load_python_forward(args.python_forward)
    pine = load_pine_export(args.pine_export) if args.pine_export else pd.DataFrame()

    if py.empty:
        pd.DataFrame(columns=COLUMNS).to_csv(args.output, index=False)
        print({"forward_parity": STATUS_PENDING, "python_events": 0, "pine_events": len(pine), "output": str(args.output)})
        return

    cmp_df = compare_forward(py, pine)
    cmp_df.to_csv(args.output, index=False)
    n = len(cmp_df)
    matches = int((cmp_df["status"] == STATUS_MATCH).sum()) if n else 0
    status = STATUS_PENDING if pine.empty else (STATUS_MATCH if matches == n and n > 0 else "FAIL")
    print({"forward_parity": status, "compared": n, "matches": matches, "output": str(args.output)})


if __name__ == "__main__":
    main()
