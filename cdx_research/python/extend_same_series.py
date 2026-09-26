"""Download Databento NQ.v.0 ohlcv-1m after the trusted last bar.

Same semantics as phase16/download_databento.py + phase58j extension:
  dataset GLBX.MDP3, schema ohlcv-1m, stype_in continuous, symbol NQ.v.0.

Writes a NEW append file. Does not overwrite phase58j until merge is audited.
Requires DATABENTO_API_KEY. Never prints the key.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "phase58j" / "data" / "nq_continuous_1m_lw_extension.csv"
OUT_DIR = ROOT / "cdx_research" / "data"


def last_bar_utc_plus_1m() -> str:
    import pandas as pd

    raw = pd.read_csv(EXT, usecols=["timestamp"])
    ts = pd.to_datetime(raw["timestamp"], utc=True).max()
    return (ts + pd.Timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-utc", default="2026-09-22T03:59:00", help="exclusive Databento end (UTC)")
    ap.add_argument("--max-cost-usd", type=float, default=5.0)
    args = ap.parse_args()
    if not os.environ.get("DATABENTO_API_KEY", "").strip():
        print("DATABENTO_API_KEY missing — cannot extend same series")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "nq_continuous_1m_lw_extension_sep2026.csv"
    start = last_bar_utc_plus_1m()
    cmd = [
        sys.executable,
        str(ROOT / "phase16" / "download_databento.py"),
        "--start",
        start,
        "--end",
        args.end_utc,
        "--symbols",
        "NQ.v.0",
        "--output",
        str(dest),
        "--chunk-days",
        "7",
        "--max-cost-usd",
        str(args.max_cost_usd),
    ]
    print("download", start, "->", args.end_utc, "out", dest)
    subprocess.run(cmd, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
