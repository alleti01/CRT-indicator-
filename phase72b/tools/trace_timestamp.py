#!/usr/bin/env python3
"""Forensic Python mirror trace for manual Pine ↔ Python parity."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.config import DEFAULT_CFG
from phase72b.python.event_log import events_to_dataframe


TRACE_COLS = [
    "timestamp_utc",
    "timestamp_chicago",
    "timestamp_ny",
    "bar_index",
    "open",
    "high",
    "low",
    "close",
    "atr",
    "state_before",
    "state_after",
    "in_trade",
    "trade_direction",
    "armed_direction",
    "cooldown",
    "cooldown_rem",
    "gate_open",
    "raw_long",
    "raw_short",
    "signal_long",
    "signal_short",
    "take_long",
    "take_short",
    "ctx_dir",
    "ctx_score_long",
    "ctx_score_short",
    "loc_long",
    "loc_short",
    "react_long",
    "react_short",
    "contra_long",
    "contra_short",
    "ev_total_long",
    "ev_total_short",
    "p4_result",
    "h1_result",
    "band_long",
    "dom_long",
    "enter_long",
    "enter_short",
    "entry_price",
    "stop_price",
    "target_price",
    "exit_stop",
    "exit_target",
    "exit_time",
    "reason_code",
    "known_at",
]


def find_bar_index(m1: pd.DataFrame, ts: pd.Timestamp) -> int:
    if ts.tzinfo is None:
        ts = ts.tz_localize(m1.index.tz)
    else:
        ts = ts.tz_convert(m1.index.tz)
    loc = m1.index.get_indexer([ts], method="nearest")
    if loc[0] < 0:
        raise ValueError(f"No bar near {ts}")
    return int(loc[0])


def mirror_fsm_start(m1: pd.DataFrame, center_i: int, warmup: int = DEFAULT_CFG.warmup, gap_minutes: float = 90.0) -> int:
    """Bar index to start FSM so prefix matches Pine (restart after last session gap)."""
    if center_i <= warmup:
        return warmup
    lookback = min(center_i - warmup, 10000)
    start = center_i - lookback
    idx = m1.index[start : center_i + 1]
    if len(idx) < 2:
        return warmup
    diffs = pd.Series(idx[1:] - idx[:-1]).dt.total_seconds() / 60.0
    big = diffs[diffs > gap_minutes]
    if len(big):
        pos = int(big.index[-1])
        return start + pos + 1
    return warmup


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase72B manual parity — Python forensic trace")
    ap.add_argument("--timestamp", required=True, help='Bar time e.g. "2026-08-26 13:40:00"')
    ap.add_argument("--timezone", default="America/Chicago")
    ap.add_argument("--before", type=int, default=10)
    ap.add_argument("--after", type=int, default=10)
    ap.add_argument("--csv", type=str, default="", help="Optional output CSV path")
    args = ap.parse_args()

    m1, m5, m15 = load_markets_lw()
    center = pd.Timestamp(args.timestamp, tz=args.timezone)
    if center < m1.index[0] or center > m1.index[-1]:
        print("ERROR: TV_EVENT_OUTSIDE_LOCAL_DATA")
        print(f"  Requested: {center} ({args.timezone})")
        print(f"  Local M1 range: {m1.index[0]} .. {m1.index[-1]} (Chicago)")
        print("  Cannot run OHLC→ATR→feature parity until timestamp is within local data.")
        return 2
    ci = find_bar_index(m1, center)
    mirror_start_i = mirror_fsm_start(m1, ci)
    end_i = min(len(m1) - 61, ci + args.after + 1)

    _, events, _, _ = run_mirror(m1, m5, m15, mirror_start_i, end_i)
    df = events_to_dataframe(events)
    for c in TRACE_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[TRACE_COLS]
    display = df[(df["bar_index"] >= ci - args.before) & (df["bar_index"] <= ci + args.after)]

    print("=" * 100)
    print(f"PYTHON MIRROR TRACE | center={args.timestamp} ({args.timezone}) | bar_index≈{ci}")
    print(f"FSM prefix from bar_index={mirror_start_i} | display T-{args.before} .. T+{args.after} | rows={len(display)}")
    print("Compare against TradingView Manual Parity table / AUTO labels (TV_MANUAL_REFERENCE)")
    print("Order: OHLC → ATR → FEATURES → STATE → SIGNAL → ENTRY → EXIT")
    print("=" * 100)
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 240)
    pd.set_option("display.max_colwidth", 40)
    print(display.to_string(index=False))

    if args.csv:
        out = Path(args.csv)
        out.parent.mkdir(parents=True, exist_ok=True)
        display.to_csv(out, index=False)
        print(f"\nWrote {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
