#!/usr/bin/env python3
"""Phase75 — chop/regime forensic research (observational only, no strategy changes)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase75.regime.classifier import compute_regime_frame, regime_at_time

REPORT_DIR = ROOT / "phase75" / "reports"
DATA_CSV = ROOT / "phase58j" / "data" / "nq_continuous_1m_lw_extension.csv"
TRADES_CSV = ROOT / "phase58j" / "results" / "last_week_all_canonical_trades.csv"
EVENTS_CSV = ROOT / "phase58j" / "results" / "last_week_event_stream.csv"


def load_bars(path: Path, tail: int = 15000) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp")
    if tail:
        df = df.tail(tail)
    df = df.set_index("timestamp")
    return df


def analyze_trades(trades: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, t in trades.iterrows():
        ts = pd.Timestamp(t["entry_ts_mgmt"])
        snap = regime_at_time(regime_df, ts)
        rows.append(
            {
                "trade_id": t["trade_id"],
                "direction": t["direction"],
                "entry_ts": ts.isoformat(),
                "net_R_m0": float(t["net_R_m0"]),
                "exit_reason_m0": t["exit_reason_m0"],
                "market_state": t.get("market_state", ""),
                "15m_state": t.get("15m_state", t.get("15m_state_mgmt", "")),
                "5m_state": t.get("5m_state", ""),
                "total_evidence": t.get("total_evidence", ""),
                "reason_codes": str(t.get("reason_codes", ""))[:120],
                "bar_regime": snap.regime,
                "efficiency": snap.efficiency,
                "atr_ratio": snap.atr_ratio,
                "overlap_ratio": snap.overlap_ratio,
            }
        )
    return pd.DataFrame(rows)


def analyze_events(events: pd.DataFrame, regime_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, e in events.iterrows():
        ts = pd.Timestamp(e["timestamp"])
        snap = regime_at_time(regime_df, ts)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "decision": e["decision"],
                "direction": e["direction"],
                "15m_state": e.get("15m_state", ""),
                "5m_state": e.get("5m_state", ""),
                "total_evidence": e.get("total_evidence", ""),
                "bar_regime": snap.regime,
                "efficiency": snap.efficiency,
            }
        )
    return pd.DataFrame(rows)


def summarize(trades: pd.DataFrame, events: pd.DataFrame) -> dict:
    def _agg(df: pd.DataFrame, col: str) -> list[dict]:
        if df.empty:
            return []
        g = df.groupby(col, dropna=False)
        out = []
        for key, sub in g:
            out.append(
                {
                    "bucket": str(key),
                    "n": int(len(sub)),
                    "mean_net_R": float(sub["net_R_m0"].mean()) if "net_R_m0" in sub else None,
                    "win_rate": float((sub["net_R_m0"] > 0).mean()) if "net_R_m0" in sub else None,
                }
            )
        return sorted(out, key=lambda x: x["n"], reverse=True)

    take = events[events["decision"] == "TAKE"] if not events.empty else events
    return {
        "trades_by_bar_regime": _agg(trades, "bar_regime"),
        "trades_by_market_state": _agg(trades, "market_state"),
        "trades_by_15m_state": _agg(trades, "15m_state"),
        "take_events_by_bar_regime": (
            take.groupby("bar_regime").size().to_dict() if not take.empty else {}
        ),
        "take_events_by_15m_neutral": int((take["15m_state"] == "NEUTRAL").sum()) if not take.empty else 0,
        "take_events_total": int(len(take)),
        "pass_wait_total": int(len(events[events["decision"].isin(["PASS", "WAIT"])])) if not events.empty else 0,
        "trade_count": int(len(trades)),
        "overall_mean_net_R": float(trades["net_R_m0"].mean()) if not trades.empty else None,
        "chop_trade_mean_R": float(trades.loc[trades["bar_regime"] == "CHOP", "net_R_m0"].mean())
        if (trades["bar_regime"] == "CHOP").any()
        else None,
        "trend_trade_mean_R": float(trades.loc[trades["bar_regime"] == "TREND", "net_R_m0"].mean())
        if (trades["bar_regime"] == "TREND").any()
        else None,
    }


def write_report(summary: dict, trades: pd.DataFrame, events: pd.DataFrame) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_md = REPORT_DIR / "PHASE75_CHOP_REGIME_RESEARCH.md"
    lines = [
        "# Phase75 — Chop / Regime Research",
        "",
        "**Mode:** Observational only — no strategy or shadow behavior changes.",
        "",
        "## Summary",
        "",
        f"- Canonical TAKE trades analyzed: **{summary['trade_count']}**",
        f"- Event stream decisions: **{summary['take_events_total']}** TAKE, **{summary['pass_wait_total']}** PASS/WAIT",
        f"- Overall mean M0 net R: **{summary['overall_mean_net_R']:.3f}**"
        if summary["overall_mean_net_R"] is not None
        else "- Overall mean M0 net R: n/a",
        "",
        "### M0 net R by bar regime (30m efficiency classifier)",
        "",
        "| Regime | n | mean net R | win rate |",
        "|--------|---|------------|----------|",
    ]
    for row in summary["trades_by_bar_regime"]:
        mr = f"{row['mean_net_R']:.3f}" if row["mean_net_R"] is not None else "n/a"
        wr = f"{row['win_rate']:.1%}" if row["win_rate"] is not None else "n/a"
        lines.append(f"| {row['bucket']} | {row['n']} | {mr} | {wr} |")

    lines.extend(
        [
            "",
            "### M0 net R by Pine `market_state`",
            "",
            "| market_state | n | mean net R | win rate |",
            "|--------------|---|------------|----------|",
        ]
    )
    for row in summary["trades_by_market_state"]:
        mr = f"{row['mean_net_R']:.3f}" if row["mean_net_R"] is not None else "n/a"
        wr = f"{row['win_rate']:.1%}" if row["win_rate"] is not None else "n/a"
        lines.append(f"| {row['bucket']} | {row['n']} | {mr} | {wr} |")

    lines.extend(
        [
            "",
            "### TAKE events by bar regime",
            "",
            str(summary["take_events_by_bar_regime"]),
            "",
            f"- TAKE with 15m NEUTRAL: **{summary['take_events_by_15m_neutral']}** / {summary['take_events_total']}",
            "",
            "## Findings (auto)",
            "",
        ]
    )

    chop_r = summary.get("chop_trade_mean_R")
    trend_r = summary.get("trend_trade_mean_R")
    if chop_r is not None and trend_r is not None:
        lines.append(
            f"- **CHOP bar regime** mean R ({chop_r:.2f}) vs **TREND** ({trend_r:.2f}) — "
            + ("CHOP underperforms; candidate for `PASS_REGIME` gate research." if chop_r < trend_r else "mixed; gate not obvious from R alone.")
        )
    uncertain = next((r for r in summary["trades_by_market_state"] if r["bucket"] == "UNCERTAIN"), None)
    if uncertain and uncertain.get("mean_net_R") is not None:
        lines.append(
            f"- Pine `market_state=UNCERTAIN` trades: n={uncertain['n']}, mean R={uncertain['mean_net_R']:.2f}."
        )

    lines.extend(
        [
            "",
            "## Next step (after FORWARD_SHADOW_PASS)",
            "",
            "Shadow-log `regime_observed` on live signals; test `WOULD_PASS_REGIME` without changing Pine.",
            "",
            "## Artifacts",
            "",
            "- `phase75/reports/chop_regime_trades.csv`",
            "- `phase75/reports/chop_regime_events.csv`",
            "- `phase75/reports/chop_regime_summary.json`",
            "",
        ]
    )
    out_md.write_text("\n".join(lines))
    return out_md


def main() -> int:
    print("Loading bars...", DATA_CSV)
    bars = load_bars(DATA_CSV)
    print(f"  {len(bars)} bars")
    regime_df = compute_regime_frame(bars)
    chop_pct = (regime_df["regime"] == "CHOP").mean()
    trend_pct = (regime_df["regime"] == "TREND").mean()
    print(f"  bar regime mix: CHOP={chop_pct:.1%} TREND={trend_pct:.1%} UNCERTAIN={1-chop_pct-trend_pct:.1%}")

    trades = pd.read_csv(TRADES_CSV)
    events = pd.read_csv(EVENTS_CSV)
    trade_df = analyze_trades(trades, regime_df)
    event_df = analyze_events(events, regime_df)
    summary = summarize(trade_df, event_df)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    trade_df.to_csv(REPORT_DIR / "chop_regime_trades.csv", index=False)
    event_df.to_csv(REPORT_DIR / "chop_regime_events.csv", index=False)
    (REPORT_DIR / "chop_regime_summary.json").write_text(json.dumps(summary, indent=2))

    md = write_report(summary, trade_df, event_df)
    print(json.dumps(summary, indent=2))
    print(f"Report: {md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
