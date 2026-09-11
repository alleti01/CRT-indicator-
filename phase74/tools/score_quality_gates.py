#!/usr/bin/env python3
"""Replay quality gates against paper_trades.csv + bars.csv (no live changes)."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase73.market_data.bar import Bar
from phase74.quality.gates import QualityGateConfig, evaluate_quality_gates


def _parse_ts(value: str) -> datetime:
    value = (value or "").strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_bars(path: Path) -> tuple[list[Bar], list[float]]:
    bars: list[Bar] = []
    atrs: list[float] = []
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            ts = _parse_ts(row["timestamp_utc"])
            bars.append(
                Bar(
                    ts,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row.get("volume") or 0),
                )
            )
            try:
                atrs.append(float(row.get("atr") or 0))
            except ValueError:
                atrs.append(0.0)
    return bars, atrs


def _window(bars: list[Bar], atrs: list[float], signal_ts: datetime, n: int) -> tuple[list[Bar], float]:
    eligible = [(b, a) for b, a in zip(bars, atrs) if b.timestamp <= signal_ts]
    if not eligible:
        return [], 0.0
    chunk = eligible[-n:]
    win = [p[0] for p in chunk]
    atr = next((p[1] for p in reversed(chunk) if p[1] > 0), 0.0)
    return win, atr


def _max_dd(rs: list[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def main() -> int:
    ap = argparse.ArgumentParser(description="Score quality gates on historical paper trades")
    ap.add_argument("--bars", default="phase74/logs/bars.csv")
    ap.add_argument("--trades", default="phase74/logs/paper_trades.csv")
    args = ap.parse_args()

    bars_path = Path(args.bars)
    trades_path = Path(args.trades)
    bars, atrs = _load_bars(bars_path)
    cfg = QualityGateConfig()

    unfiltered: list[float] = []
    kept: list[float] = []
    reasons: Counter[str] = Counter()
    rows_out: list[str] = []

    with trades_path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                net_r = float(row.get("net_R") or 0)
            except ValueError:
                continue
            direction = row.get("direction", "")
            sig_raw = row.get("signal_timestamp") or row.get("entry_timestamp") or ""
            try:
                sig_ts = _parse_ts(sig_raw)
            except ValueError:
                continue
            win, atr = _window(bars, atrs, sig_ts, cfg.lookback_bars)
            if atr <= 0:
                try:
                    atr = float(row.get("atr") or 0)
                except ValueError:
                    atr = 0.0
            dec = evaluate_quality_gates(win, direction, atr, cfg)
            reasons[dec.reason] += 1
            unfiltered.append(net_r)
            kept_flag = dec.decision == "TAKE"
            if kept_flag:
                kept.append(net_r)
            rows_out.append(
                f"{sig_ts.isoformat()} {direction:5} {net_r:+6.2f}R  {dec.reason:18} "
                f"box={dec.box_atr:.2f}ATR prog={dec.progress_atr:.2f}ATR"
            )

    def _stats(rs: list[float]) -> str:
        if not rs:
            return "n=0"
        wins = sum(1 for r in rs if r > 0)
        losses = sum(1 for r in rs if r < 0)
        return (
            f"n={len(rs)} W/L={wins}/{losses} net={sum(rs):+.2f}R "
            f"maxDD={_max_dd(rs):+.2f}R"
        )

    print("UNFILTERED ", _stats(unfiltered))
    print("GATED      ", _stats(kept))
    print("SKIPS      ", dict(reasons))
    print()
    for line in rows_out:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
