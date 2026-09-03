#!/usr/bin/env python3
"""Compute Phase51 forward metrics and checkpoint reports from trades.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from phase51.config import (
    BENCHMARK_AVG_R,
    BENCHMARK_FILL_RATE,
    BENCHMARK_MAX_DD,
    BENCHMARK_MEDIAN_DELAY_MIN,
    BENCHMARK_N,
    BENCHMARK_PF,
    CHECKPOINTS,
    FORWARD_DIR,
    RESULTS_DIR,
    TIMEZONE,
)

TRADES_PATH = FORWARD_DIR / "trades.csv"
B1_PATH = FORWARD_DIR / "b1_events.csv"
P44_PATH = FORWARD_DIR / "phase44_signals.csv"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size <= len(path.read_text().splitlines()[0]) + 2:
        return pd.DataFrame()
    return pd.read_csv(path)


def realized_r(row: pd.Series) -> float:
    entry, stop, exit_px = row["entry_price"], row["stop_price"], row["exit_price"]
    direction = 1 if str(row["direction"]).upper() == "LONG" else -1
    risk = abs(entry - stop)
    if risk <= 0 or not np.isfinite(risk):
        return np.nan
    return direction * (exit_px - entry) / risk


def max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return np.nan
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    return float(np.nanmax(dd)) if len(dd) else np.nan


def metrics_for(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"N": 0}
    rs = df["realized_r"].astype(float)
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    pf = wins.sum() / abs(losses.sum()) if len(losses) and losses.sum() != 0 else np.nan
    eq = np.cumsum(rs.fillna(0))
    return {
        "N": int(len(df)),
        "AvgR": float(rs.mean()) if len(rs) else np.nan,
        "median_R": float(rs.median()) if len(rs) else np.nan,
        "PF": float(pf) if np.isfinite(pf) else np.nan,
        "TotalR": float(rs.sum()) if len(rs) else np.nan,
        "win_rate": float((rs > 0).mean()) if len(rs) else np.nan,
        "MaxDD": max_drawdown(eq),
    }


def fill_rate(p44: pd.DataFrame, b1: pd.DataFrame) -> float:
    if p44.empty:
        return np.nan
    confirmed = b1.loc[b1.get("confirmed", True).astype(bool)] if not b1.empty else pd.DataFrame()
    return len(confirmed) / len(p44) if len(p44) else np.nan


def median_b1_delay(b1: pd.DataFrame) -> float:
    if b1.empty or "delay_minutes" not in b1.columns:
        return np.nan
    s = pd.to_numeric(b1["delay_minutes"], errors="coerce").dropna()
    return float(s.median()) if len(s) else np.nan


def write_checkpoint(n: int, trades: pd.DataFrame, p44: pd.DataFrame, b1: pd.DataFrame) -> None:
    subset = trades.head(n) if len(trades) >= n else trades
    m = metrics_for(subset)
    path = RESULTS_DIR / f"checkpoint_{n}.md"
    lines = [
        f"# Phase51 Checkpoint — {n} closed trades",
        "",
        f"Trades available: {len(trades)} (report uses first {len(subset)})",
        "",
        "## Aggregate",
        "",
    ]
    for k, v in m.items():
        lines.append(f"- **{k}**: {v}")
    lines.extend(
        [
            "",
            "## Benchmark reference (Phase45 B1 — not targets)",
            "",
            f"- N = {BENCHMARK_N}",
            f"- AvgR = {BENCHMARK_AVG_R}",
            f"- PF = {BENCHMARK_PF}",
            f"- MaxDD = {BENCHMARK_MAX_DD}",
            f"- Fill rate = {BENCHMARK_FILL_RATE * 100:.1f}%",
            f"- Median B1 delay = {BENCHMARK_MEDIAN_DELAY_MIN} min",
            "",
            "## Phase44 → B1",
            "",
            f"- Fill rate: {fill_rate(p44, b1):.3f}" if not p44.empty else "- Fill rate: n/a",
            f"- Median B1 delay: {median_b1_delay(b1):.1f} min" if not b1.empty else "- Median B1 delay: n/a",
            "",
            "## By direction",
            "",
        ]
    )
    if subset.empty or "direction" not in subset.columns:
        lines.append("_No closed forward trades yet._")
    else:
        for side in ("LONG", "SHORT"):
            sub = subset.loc[subset["direction"].astype(str).str.upper() == side]
            sm = metrics_for(sub)
            lines.append(f"### {side}: N={sm.get('N', 0)}, AvgR={sm.get('AvgR', 'n/a')}, PF={sm.get('PF', 'n/a')}")
    lines.append("")
    lines.append("_Do not optimize at checkpoints — evaluate only._")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", type=Path, default=TRADES_PATH)
    args = parser.parse_args()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    trades = _read(args.trades)
    p44 = _read(P44_PATH)
    b1 = _read(B1_PATH)
    if not trades.empty and "realized_r" not in trades.columns:
        trades = trades.copy()
        trades["realized_r"] = trades.apply(realized_r, axis=1)
    m = metrics_for(trades)
    row = {
        **m,
        "fill_rate": fill_rate(p44, b1),
        "median_b1_delay_min": median_b1_delay(b1),
        "forward_trades": len(trades),
        "forward_p44": len(p44),
    }
    pd.DataFrame([row]).to_csv(RESULTS_DIR / "current_forward_metrics.csv", index=False)
    for cp in CHECKPOINTS:
        write_checkpoint(cp, trades, p44, b1)
    print(f"Wrote {RESULTS_DIR / 'current_forward_metrics.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
