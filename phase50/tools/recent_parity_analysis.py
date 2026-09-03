#!/usr/bin/env python3
"""Recent TradingView-accessible parity analysis for Phase50."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase50.config import FROZEN_B1_WINDOW_MIN, RESULTS, TIMEZONE

REF_PATH = RESULTS / "python_reference_signals.csv"
OUT_MANUAL = RESULTS / "recent_manual_test_signals.csv"
OUT_REPORT = RESULTS / "recent_parity_report.md"


def _load_ref(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        parse_dates=["phase44_timestamp", "b1_timestamp", "entry_timestamp", "actionable_timestamp"],
    )
    for c in ("phase44_timestamp", "b1_timestamp", "entry_timestamp", "actionable_timestamp"):
        df[c] = pd.to_datetime(df[c], utc=True).dt.tz_convert(TIMEZONE)
    return df.sort_values("entry_timestamp", ascending=False).reset_index(drop=True)


def _trading_days(df: pd.DataFrame) -> list:
    return sorted(df["entry_timestamp"].dt.date.unique())


def _count_last_n_days(df: pd.DataFrame, n: int) -> int:
    days = _trading_days(df)
    sel = set(days[-n:])
    return int(df.loc[df["entry_timestamp"].dt.date.isin(sel)].shape[0])


def _select_manual(df: pd.DataFrame, n_long: int = 5, n_short: int = 5) -> pd.DataFrame:
    longs = df.loc[df["direction"].str.lower() == "long"].head(n_long)
    shorts = df.loc[df["direction"].str.lower() == "short"].head(n_short)
    out = pd.concat([longs, shorts], ignore_index=True)
    return out.sort_values("entry_timestamp", ascending=False)


def _fmt_ct(ts: pd.Timestamp) -> tuple[str, str]:
    t = ts.tz_convert(TIMEZONE)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _marker(side: str) -> str:
    return "green triangle" if side.lower() == "long" else "red triangle"


def _trace_event(row: pd.Series, market: pd.DataFrame, pos: dict) -> dict:
    p44 = row["phase44_timestamp"]
    act = row["actionable_timestamp"]
    end = act + pd.Timedelta(minutes=FROZEN_B1_WINDOW_MIN)
    direction = str(row["direction"])
    fill = confirm_b1(market, pos, act, FROZEN_B1_WINDOW_MIN, direction)

    pine_p44 = "p44Fill>0 on first 1M bar after 15M fill (request.security lookahead_off)"
    pine_p44_evt = f"YES — marker {p44.strftime('%Y-%m-%d %H:%M %Z')}"
    pine_win_start = act.strftime("%Y-%m-%d %H:%M %Z")
    pine_win_end = end.strftime("%Y-%m-%d %H:%M %Z")
    pine_b1 = f"close {'>' if direction.lower()=='long' else '<'} causalSwing on 1M in [{pine_win_start}, {pine_win_end}]"
    pine_entry = "YES — p50PlotLongB1/p50PlotShortB1 plotshape" if fill.filled else "NO — B1 not filled in window"

    status = "MATCH" if fill.filled and fill.entry_time == row["entry_timestamp"] else "FAIL"
    if fill.filled and abs((fill.entry_time - row["entry_timestamp"]).total_seconds()) <= 60:
        status = "MATCH"

    return {
        "reference_signal_id": row["signal_id"],
        "reference_side": direction,
        "reference_phase44_time": p44.isoformat(),
        "reference_b1_time": row["b1_timestamp"].isoformat(),
        "pine_phase44_condition": pine_p44,
        "pine_phase44_event": pine_p44_evt,
        "pine_window_start": pine_win_start,
        "pine_window_end": pine_win_end,
        "pine_b1_condition": pine_b1,
        "pine_entry_event": pine_entry,
        "expected_pine_result": status,
    }


def build_report(ref: pd.DataFrame, manual: pd.DataFrame, traces: list[dict]) -> str:
    latest = ref.iloc[0]
    d, t = _fmt_ct(latest["entry_timestamp"])
    lines = [
        "# Phase50 Recent Parity Report",
        "",
        "## 20 Most Recent Reference Trades",
        "",
        "| signal_id | date | phase44_timestamp | b1_timestamp | entry_timestamp | direction | class | setup |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in ref.head(20).iterrows():
        dd, _ = _fmt_ct(r["entry_timestamp"])
        lines.append(
            f"| {r['signal_id']} | {dd} | {r['phase44_timestamp']} | {r['b1_timestamp']} | {r['entry_timestamp']} | {r['direction']} | {r['phase44_class']} | {r['setup_type']} |"
        )

    lines += ["", "## Manual Test Table", "", "DATE | TIME CT | SIDE | EXPECTED MARKER", "---|---|---|---"]
    for _, r in manual.sort_values("entry_timestamp", ascending=False).iterrows():
        dd, tt = _fmt_ct(r["entry_timestamp"])
        lines.append(f"{dd} | {tt} | {r['direction'].upper()} | {_marker(r['direction'])}")

    lines += ["", "## Pine Trace (10 manual trades)", ""]
    for tr in traces:
        lines += [
            f"### {tr['reference_signal_id']} ({tr['reference_side']})",
            f"- REFERENCE PHASE44 TIME: {tr['reference_phase44_time']}",
            f"- REFERENCE B1 TIME: {tr['reference_b1_time']}",
            f"- PINE PHASE44 CONDITION: {tr['pine_phase44_condition']}",
            f"- PINE PHASE44 EVENT: {tr['pine_phase44_event']}",
            f"- PINE WINDOW START: {tr['pine_window_start']}",
            f"- PINE WINDOW END: {tr['pine_window_end']}",
            f"- PINE B1 CONDITION: {tr['pine_b1_condition']}",
            f"- PINE ENTRY EVENT: {tr['pine_entry_event']}",
            f"- EXPECTED PINE RESULT: **{tr['expected_pine_result']}**",
            "",
        ]

    c1, c3, c5, c10, c20 = (_count_last_n_days(ref, n) for n in (1, 3, 5, 10, 20))
    lines += [
        "## Signal Density (canonical B1@10min)",
        "",
        "| WINDOW | EXPECTED SIGNAL COUNT |",
        "|---|---|",
        f"| last 1 trading day | {c1} |",
        f"| last 3 trading days | {c3} |",
        f"| last 5 trading days | {c5} |",
        f"| last 10 trading days | {c10} |",
        f"| last 20 trading days | {c20} |",
        "",
        "## Final Summary",
        "",
        f"**MOST RECENT PYTHON SIGNAL:** {latest['entry_timestamp']} {latest['direction']} ({latest['signal_id']})",
        f"**EXPECTED SIGNALS LAST 5 DAYS:** {c5}",
        f"**EXPECTED SIGNALS LAST 10 DAYS:** {c10}",
        f"**EXPECTED SIGNALS LAST 20 DAYS:** {c20}",
        "",
        "**RECENT MANUAL TEST DATES:**",
    ]
    for _, r in manual.sort_values("entry_timestamp", ascending=False).iterrows():
        dd, tt = _fmt_ct(r["entry_timestamp"])
        lines.append(f"- {dd} {tt} CT — {r['direction'].upper()} ({r['signal_id']})")

    should_show = c10 > 0
    lines += [
        "",
        f"**CURRENT PINE SHOULD SHOW SIGNALS IN ACCESSIBLE RANGE:** {'YES' if should_show else 'NO'}",
        "",
    ]
    if should_show:
        lines += [
            "**IF YES AND TRADINGVIEW SHOWS ZERO:** PHASE50 STATUS = FAIL",
            "",
            "**FIRST LIKELY FAILURE STAGE:** Phase44 (15M security state) or plotting — verify Debug mode counters",
            "",
        ]
    else:
        lines += ["Zero Pine markers in visible window may be legitimate (no Python signals).", ""]

    lines += ["**STRATEGY LOGIC CHANGED:** NO", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", type=Path, default=REF_PATH)
    parser.add_argument("--manual-out", type=Path, default=OUT_MANUAL)
    parser.add_argument("--report-out", type=Path, default=OUT_REPORT)
    args = parser.parse_args()

    ref = _load_ref(args.ref)
    manual = _select_manual(ref)
    manual_out = manual[
        [
            "signal_id",
            "entry_timestamp",
            "phase44_timestamp",
            "b1_timestamp",
            "direction",
            "phase44_class",
            "setup_type",
        ]
    ].copy()
    manual_out.insert(1, "date", manual_out["entry_timestamp"].dt.date.astype(str))
    manual_out.to_csv(args.manual_out, index=False)

    market = load_market_1m()
    pos = {ts: i for i, ts in enumerate(market.index)}
    traces = [_trace_event(r, market, pos) for _, r in manual.iterrows()]

    report = build_report(ref, manual, traces)
    args.report_out.write_text(report)

    latest = ref.iloc[0]
    print("=== 20 MOST RECENT (newest first) ===")
    show = ref.head(20)[
        ["signal_id", "entry_timestamp", "phase44_timestamp", "b1_timestamp", "direction", "phase44_class", "setup_type"]
    ]
    for _, r in show.iterrows():
        d, t = _fmt_ct(r["entry_timestamp"])
        print(
            f"{r['signal_id']} | {d} | {r['phase44_timestamp']} | {r['b1_timestamp']} | {r['entry_timestamp']} | {r['direction']} | {r['phase44_class']} | {r['setup_type']}"
        )

    print("\n=== MANUAL TEST TABLE ===")
    print("DATE | TIME CT | SIDE | EXPECTED MARKER")
    for _, r in manual.sort_values("entry_timestamp", ascending=False).iterrows():
        d, t = _fmt_ct(r["entry_timestamp"])
        print(f"{d} | {t} | {r['direction'].upper()} | {_marker(r['direction'])}")

    for n in (1, 3, 5, 10, 20):
        print(f"EXPECTED last {n} trading days: {_count_last_n_days(ref, n)}")

    print(f"\nMOST RECENT PYTHON SIGNAL: {latest['entry_timestamp']} {latest['direction']}")
    print(f"wrote {args.manual_out}")
    print(f"wrote {args.report_out}")


if __name__ == "__main__":
    main()
