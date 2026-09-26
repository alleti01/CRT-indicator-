"""Replay sideways overlay on paper fills. Does not touch LiveStack."""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from phase73.market_data.bar import Bar
from phase74.config.loader import load_phase74_config
from phase74.quality.gates import QualityGateConfig
from phase74.quality.sideways import SidewaysOverlayConfig
from phase74.quality.sideways_overlay import evaluate_quality_with_sideways

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "phase74" / "logs"
WEEK_START = datetime(2026, 9, 14, tzinfo=ET)
WEEK_END = datetime(2026, 9, 19, tzinfo=ET)

EFF_GRID = (0.15, 0.25, 0.35)
OVERLAP_GRID = (0.35, 0.45, 0.55)
BUFFER_GRID = (0.0, 0.05, 0.10)


def _parse(ts: str) -> datetime:
    ts = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def load_bars() -> list[Bar]:
    out: list[Bar] = []
    with (LOGS / "bars.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.append(
                Bar(
                    timestamp=_parse(row["timestamp_utc"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"] or 0),
                )
            )
    return out


def bars_at(all_bars: list[Bar], when: datetime, need: int = 20) -> list[Bar] | None:
    end = None
    for i, b in enumerate(all_bars):
        if b.timestamp <= when:
            end = i
        else:
            break
    if end is None or end + 1 < need:
        return None
    return all_bars[: end + 1]


def load_trades(week_only: bool) -> list[dict]:
    rows = []
    with (LOGS / "paper_trades.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            et = _parse(row["entry_timestamp"]).astimezone(ET)
            if week_only and not (WEEK_START <= et < WEEK_END):
                continue
            row["_et"] = et
            row["_signal_dt"] = _parse(row["signal_timestamp"])
            row["_entry_dt"] = _parse(row["entry_timestamp"])
            row["net_r"] = float(row["net_R"])
            row["atr"] = float(row["atr"])
            row["usd"] = row["net_r"] * row["atr"] * 20.0
            rows.append(row)
    return rows


def replay_one(
    trade: dict,
    all_bars: list[Bar],
    gate_cfg: QualityGateConfig,
    overlay_cfg: SidewaysOverlayConfig,
) -> dict | None:
    hist = bars_at(all_bars, trade["_entry_dt"])
    if hist is None:
        return None
    dec = evaluate_quality_with_sideways(
        hist,
        trade["direction"],
        trade["atr"],
        signal_time=trade["_signal_dt"],
        gate_cfg=gate_cfg,
        overlay_cfg=overlay_cfg,
    )
    existing = evaluate_quality_with_sideways(
        hist,
        trade["direction"],
        trade["atr"],
        signal_time=trade["_signal_dt"],
        gate_cfg=gate_cfg,
        overlay_cfg=SidewaysOverlayConfig(enabled=False),
    )
    m = dec.metrics
    e = dec.escape
    new_r = trade["net_r"] if dec.decision == "TAKE" else 0.0
    return {
        "timestamp": trade["_et"].strftime("%Y-%m-%d %H:%M ET"),
        "session": dec.session,
        "direction": trade["direction"],
        "original_decision": existing.reason,
        "new_decision": dec.reason,
        "original_action": existing.decision,
        "new_action": dec.decision,
        "range_atr_20": None if m is None else round(m.range_atr_20, 4),
        "net_progress_20": None if m is None else round(m.net_progress_20, 4),
        "total_path_20": None if m is None else round(m.total_path_20, 4),
        "directional_efficiency_20": None
        if m is None
        else round(m.directional_efficiency_20, 4),
        "overlap": None if m is None else round(m.adjacent_overlap_ratio, 4),
        "sideways_wide_range": dec.sideways_wide_range,
        "continuation_3_of_4": False if m is None else m.continuation_3_of_4,
        "false_break": dec.false_break,
        "close_through": False if e is None else e.close_through,
        "retest_hold": False if e is None else e.retest_hold,
        "escape_state": dec.market_state,
        "original_R": round(trade["net_r"], 4),
        "new_R": round(new_r, 4),
        "original_usd": round(trade["usd"], 2),
        "new_usd": round(new_r * trade["atr"] * 20.0, 2),
    }


def summarize(rows: list[dict]) -> dict:
    orig_takes = [r for r in rows if r["original_action"] == "TAKE"]
    new_takes = [r for r in rows if r["new_action"] == "TAKE"]
    incremental = [
        r for r in rows if r["original_action"] == "TAKE" and r["new_action"] == "SKIP"
    ]
    losers_blocked = [r for r in incremental if r["original_R"] < 0]
    winners_blocked = [r for r in incremental if r["original_R"] > 0]
    orig_r = sum(r["original_R"] for r in orig_takes)
    new_r = sum(r["original_R"] for r in new_takes)
    orig_usd = sum(r["original_usd"] for r in orig_takes)
    new_usd = sum(r["original_usd"] for r in new_takes)
    gate_winners = sum(1 for r in orig_takes if r["original_R"] > 0)
    return {
        "n": len(rows),
        "original_takes": len(orig_takes),
        "new_takes": len(new_takes),
        "losers_blocked": len(losers_blocked),
        "winners_blocked": len(winners_blocked),
        "winner_retention": 1.0
        - (len(winners_blocked) / max(1, gate_winners)),
        "original_R": round(orig_r, 4),
        "new_R": round(new_r, 4),
        "net_R_delta": round(new_r - orig_r, 4),
        "original_usd": round(orig_usd, 2),
        "new_usd": round(new_usd, 2),
        "blocked_winner_R": round(sum(r["original_R"] for r in winners_blocked), 4),
        "blocked_loser_R": round(sum(r["original_R"] for r in losers_blocked), 4),
        "blocked_winners": [r["timestamp"] + " " + r["direction"] for r in winners_blocked],
        "blocked_losers": [r["timestamp"] + " " + r["direction"] for r in losers_blocked],
    }


def run_grid(trades: list[dict], all_bars: list[Bar], gate_cfg: QualityGateConfig) -> list[dict]:
    cells = []
    for eff in EFF_GRID:
        for ov in OVERLAP_GRID:
            for buf in BUFFER_GRID:
                cfg = SidewaysOverlayConfig(
                    enabled=True,
                    apply_outside_rth_only=True,
                    efficiency_max=eff,
                    overlap_min=ov,
                    close_through_buffer_atr=buf,
                )
                rows = [replay_one(t, all_bars, gate_cfg, cfg) for t in trades]
                rows = [r for r in rows if r is not None]
                s = summarize(rows)
                s["efficiency_max"] = eff
                s["overlap_min"] = ov
                s["buffer_atr"] = buf
                cells.append(s)
    return cells


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-trades", action="store_true")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    cfg = load_phase74_config(ROOT / "phase74" / "config" / "default.json")
    gate_cfg = QualityGateConfig.from_dict(cfg.section("quality_gates"))
    overlay = SidewaysOverlayConfig(enabled=True, apply_outside_rth_only=True)
    all_bars = load_bars()
    trades = load_trades(week_only=not args.all_trades)
    rows = [replay_one(t, all_bars, gate_cfg, overlay) for t in trades]
    rows = [r for r in rows if r is not None]
    report = {
        "sample": "last_week_18" if not args.all_trades else "all_paper_fills",
        "overlay": {
            "efficiency_max": overlay.efficiency_max,
            "overlap_min": overlay.overlap_min,
            "close_through_buffer_atr": overlay.close_through_buffer_atr,
        },
        "trades": rows,
        "summary": summarize(rows),
        "grid": run_grid(trades, all_bars, gate_cfg),
    }
    text = json.dumps(report, indent=2)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
