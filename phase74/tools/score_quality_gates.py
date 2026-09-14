#!/usr/bin/env python3
"""Replay quality gates + prop dollar card against paper_trades.csv (NQ $20/point)."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase73.market_data.bar import Bar
from phase74.quality.day_halt import PropDayHalt, nq_dollars, session_date_ny
from phase74.quality.gates import QualityGateConfig, evaluate_quality_gates

_NY = ZoneInfo("America/New_York")
POINT_VALUE = 20.0


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


def _max_dd(xs: list[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for x in xs:
        eq += x
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def _stats_r(rs: list[float]) -> str:
    if not rs:
        return "n=0"
    wins = sum(1 for r in rs if r > 0)
    losses = sum(1 for r in rs if r < 0)
    return f"n={len(rs)} W/L={wins}/{losses} net={sum(rs):+.2f}R maxDD={_max_dd(rs):+.2f}R"


def _stats_usd(ds: list[float]) -> str:
    if not ds:
        return "n=0"
    wins = sum(1 for d in ds if d > 0)
    losses = sum(1 for d in ds if d < 0)
    return f"n={len(ds)} W/L={wins}/{losses} net=${sum(ds):+,.0f} maxDD=${_max_dd(ds):+,.0f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Score quality gates + prop dollar card")
    ap.add_argument("--bars", default="phase74/logs/bars.csv")
    ap.add_argument("--trades", default="phase74/logs/paper_trades.csv")
    args = ap.parse_args()

    bars, atrs = _load_bars(Path(args.bars))
    cfg = QualityGateConfig()
    halt = PropDayHalt()

    unfiltered_r: list[float] = []
    unfiltered_usd: list[float] = []
    gated_r: list[float] = []
    gated_usd: list[float] = []
    card_r: list[float] = []
    card_usd: list[float] = []
    reasons: Counter[str] = Counter()
    by_day: dict[str, list[tuple[str, float, float, str]]] = defaultdict(list)
    rows_out: list[str] = []

    trades: list[dict[str, str]] = []
    with Path(args.trades).open(encoding="utf-8", newline="") as f:
        trades = list(csv.DictReader(f))
    trades.sort(key=lambda r: r.get("entry_timestamp") or r.get("signal_timestamp") or "")

    for row in trades:
        try:
            net_r = float(row.get("net_R") or 0)
            atr = float(row.get("atr") or 0)
        except ValueError:
            continue
        direction = row.get("direction", "")
        sig_raw = row.get("signal_timestamp") or row.get("entry_timestamp") or ""
        try:
            sig_ts = _parse_ts(sig_raw)
        except ValueError:
            continue
        win, bar_atr = _window(bars, atrs, sig_ts, cfg.lookback_bars)
        live_atr = bar_atr if bar_atr > 0 else atr
        dollars = nq_dollars(net_r, atr if atr > 0 else live_atr, POINT_VALUE)
        dec = evaluate_quality_gates(win, direction, live_atr if live_atr > 0 else atr, cfg)
        ny = session_date_ny(sig_ts).isoformat()

        unfiltered_r.append(net_r)
        unfiltered_usd.append(dollars)

        if dec.decision == "TAKE":
            gated_r.append(net_r)
            gated_usd.append(dollars)
            if halt.should_halt_new_entries(sig_ts):
                reason = halt.reason
                reasons[reason] += 1
                status = reason
            else:
                card_r.append(net_r)
                card_usd.append(dollars)
                halt.record_closed(net_r, sig_ts, dollars=dollars)
                reason = dec.reason
                reasons[reason] += 1
                status = "KEEP"
        else:
            reasons[dec.reason] += 1
            status = dec.reason

        by_day[ny].append((status, net_r, dollars, direction))
        rows_out.append(
            f"{sig_ts.astimezone(_NY).strftime('%Y-%m-%d %H:%M ET')} {direction:5} "
            f"{net_r:+6.2f}R ${dollars:+8.0f}  {status:18} atr={atr:.1f}"
        )

    print("UNFILTERED ", _stats_r(unfiltered_r), _stats_usd(unfiltered_usd))
    print("GATES ONLY ", _stats_r(gated_r), _stats_usd(gated_usd))
    print("PROP CARD  ", _stats_r(card_r), _stats_usd(card_usd))
    print("REASONS    ", dict(reasons))
    print()
    for day, items in by_day.items():
        kept = [(r, d) for st, r, d, _ in items if st == "KEEP"]
        print(
            f"NY {day}  kept {len(kept)}  "
            f"R={sum(r for r, _ in kept):+.2f}  "
            f"${sum(d for _, d in kept):+,.0f}"
        )
    print()
    for line in rows_out:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
