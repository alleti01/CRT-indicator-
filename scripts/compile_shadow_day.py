#!/usr/bin/env python3
"""Compile Phase74 shadow rehearsal data for a single UTC calendar day."""
from __future__ import annotations

import ast
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "phase74" / "logs"
OUT = ROOT / "forward_rehearsal" / "reports"
ET = ZoneInfo("America/New_York")


def in_day_utc(ts: str, day: str) -> bool:
    return ts.startswith(day)


def parse_latency(row: dict) -> float | None:
    for v in row.values():
        if isinstance(v, str) and v.startswith("{") and "pine_to_webhook_ms" in v:
            try:
                return float(ast.literal_eval(v).get("pine_to_webhook_ms", 0))
            except (SyntaxError, ValueError, TypeError):
                pass
    return None


def to_et(iso: str) -> str:
    if not iso:
        return ""
    iso = iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ET).strftime("%Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return iso


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now(ET).strftime("%Y-%m-%d")
    OUT.mkdir(parents=True, exist_ok=True)

    signals_by_id: dict[str, dict] = {}
    with open(LOGS / "signals.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not in_day_utc(row.get("received_at_utc", ""), day):
                continue
            sid = row["signal_id"]
            lat = parse_latency(row)
            prev_lat = parse_latency(signals_by_id[sid]) if sid in signals_by_id else None
            if sid not in signals_by_id or (lat is not None and prev_lat is None):
                signals_by_id[sid] = row

    signals = sorted(signals_by_id.values(), key=lambda r: r["received_at_utc"])
    longs = sum(1 for s in signals if s["event"] == "SIGNAL_LONG")
    shorts = sum(1 for s in signals if s["event"] == "SIGNAL_SHORT")

    watch_bars = data_healthy = data_missing = 0
    with open(LOGS / "decisions.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not in_day_utc(row.get("timestamp_utc", ""), day):
                continue
            if row.get("action") == "WATCH":
                watch_bars += 1
            h = row.get("market_data_health", "")
            if h == "DATA_HEALTHY":
                data_healthy += 1
            elif h == "DATA_MISSING":
                data_missing += 1

    latencies = [v for v in (parse_latency(s) for s in signals) if v is not None]

    csv_path = OUT / f"{day}_shadow_signals.csv"
    fields = [
        "signal_id",
        "event",
        "signal_bar_time_utc",
        "signal_time_utc",
        "signal_price",
        "context",
        "received_at_utc",
        "received_et",
        "pine_to_webhook_ms",
        "bot_action",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for s in signals:
            ptw = parse_latency(s)
            w.writerow(
                {
                    "signal_id": s["signal_id"],
                    "event": s["event"],
                    "signal_bar_time_utc": s["signal_bar_time_utc"],
                    "signal_time_utc": s["signal_time_utc"],
                    "signal_price": s["signal_price"],
                    "context": s["context"],
                    "received_at_utc": s["received_at_utc"],
                    "received_et": to_et(s["received_at_utc"]),
                    "pine_to_webhook_ms": "" if ptw is None else f"{ptw:.1f}",
                    "bot_action": "WOULD_ENTER",
                }
            )

    md_path = OUT / f"{day}_SHADOW_DAY_DIGEST.md"
    lines = [
        f"# Phase74 Shadow Rehearsal — {day}",
        "",
        f"Compiled: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        "## Summary",
        "",
        f"- **Webhooks accepted:** {len(signals)}",
        f"- **LONG signals:** {longs}",
        f"- **SHORT signals:** {shorts}",
        f"- **Shadow action:** WOULD_ENTER on all accepted signals",
        f"- **Watch bars logged:** {watch_bars}",
        f"- **Bars DATA_HEALTHY:** {data_healthy}",
        f"- **Bars DATA_MISSING:** {data_missing}",
    ]
    if latencies:
        lines.append(
            f"- **Webhook latency (ms):** min={min(latencies):.0f}, "
            f"max={max(latencies):.0f}, avg={sum(latencies)/len(latencies):.0f}"
        )
    lines += [
        "",
        "## Signal log (ET)",
        "",
        "| # | Received (ET) | Event | Price | Bar (ET) | signal_id | Latency ms |",
        "|---|---------------|-------|-------|----------|-----------|------------|",
    ]
    for i, s in enumerate(signals, 1):
        ptw = parse_latency(s)
        sid = s["signal_id"]
        sid_short = sid if len(sid) <= 28 else sid[:25] + "..."
        lat_str = "" if ptw is None else f"{ptw:.0f}"
        lines.append(
            f"| {i} | {to_et(s['received_at_utc'])} | {s['event']} | "
            f"{s['signal_price']} | {to_et(s['signal_bar_time_utc'])} | "
            f"`{sid_short}` | {lat_str} |"
        )
    lines += [
        "",
        "## Files",
        "",
        f"- Signal CSV: `{csv_path.relative_to(ROOT).as_posix()}`",
        "- Source logs: `phase74/logs/signals.csv`, `decisions.csv`, `errors.jsonl`",
        "",
        "## Notes",
        "",
        "- All trades are **shadow mode** (WOULD_ENTER — no live orders).",
        "- Contract: NQ via NinjaTrader bridge; pine_hash frozen Phase72A.",
        "- Negative latency = webhook timestamp vs bar-close alignment artifact.",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Wrote {md_path}")
    print(f"Wrote {csv_path}")
    print(f"Signals: {len(signals)} ({longs}L / {shorts}S)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
