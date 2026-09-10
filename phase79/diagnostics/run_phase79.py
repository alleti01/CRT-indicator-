#!/usr/bin/env python3
"""Phase79 — ATM management model test (management only, frozen Phase72A entries)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58b.research.simulation import metrics as sim_metrics
from phase58j.research.walkforward_audit import walkforward_splits
from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import ENTRY_SPEC, config_hash, executions, load_frozen_entries
from phase79.python.atm_walk import ATMParams, counterfactual_killed_winner_path
from phase79.python.config import (
    ATM_A,
    BASELINE,
    BASELINE_REPRO,
    CHECKPOINTS,
    EXPECTED_SIGNAL_HASH,
    REPORTS,
    ROBUSTNESS_BE_OFFSETS,
    ROBUSTNESS_BE_TRIGGERS,
    verify_pine_freeze,
)
from phase79.python.metrics import (
    compare,
    killed_winners_analysis,
    saved_losers_analysis,
    summarize,
    transition_table,
    year_breakdown,
)
from phase79.python.runner import run_atm_on_entries, run_baseline_one_position, verify_baseline_reproduction

CANON = ROOT / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"


def _save_json(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _write_report(lines: list[str]) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    p = REPORTS / "PHASE79_FINAL_REPORT.md"
    p.write_text("\n".join(lines) + "\n")
    return p


def _partition_metrics(trades: pd.DataFrame, execs_sorted: pd.DataFrame, splits: dict) -> dict:
    out = {}
    for name, (a, b) in splits.items():
        ids = set(execs_sorted.iloc[a:b]["trade_id"])
        sub = trades[trades["trade_id"].isin(ids)]
        out[name] = summarize(sub)
    return out


def _evaluate_pass(baseline_m: dict, atm_m: dict, delta: dict, year_df: pd.DataFrame, robustness: list[dict] | None) -> tuple[bool, list[str]]:
    fails = []
    if delta["DeltaAvgR"] <= 0:
        fails.append("AvgR did not improve")
    if delta["DeltaTotalR"] <= 0:
        fails.append("TotalR did not improve")
    if atm_m["PF"] < baseline_m["PF"] * 0.95:
        fails.append("PF materially deteriorated (>5%)")
    if atm_m["MaxDD"] > baseline_m["MaxDD"] * 1.10:
        fails.append("MaxDD materially worse (>10%)")
    if len(year_df) >= 3:
        pos_years = int((year_df["DeltaAvgR"] > 0).sum()) if "DeltaAvgR" in year_df else 0
        best_year_share = float(year_df["DeltaTotalR"].max() / delta["DeltaTotalR"]) if delta["DeltaTotalR"] > 0 else 1.0
        if delta["DeltaTotalR"] > 0 and best_year_share > 0.6:
            fails.append("Improvement concentrated in one year")
    for side in ("LONG", "SHORT"):
        # checked in main with side-specific delta
        pass
    if robustness:
        avgs = [r["AvgR"] for r in robustness]
        if max(avgs) - min(avgs) > 0.05 and min(avgs) < baseline_m["AvgR"]:
            fails.append("Severe robustness cliff around BE trigger")
    return len(fails) == 0, fails


def main() -> int:
    t0 = time.time()
    lines = ["# Phase79 — ATM Management Model Test", ""]

    ok, pine_hash = verify_pine_freeze()
    if not ok:
        lines += [f"**Verdict:** `PHASE79_SIGNAL_FREEZE_MISMATCH`", "", f"Pine hash mismatch: {pine_hash}"]
        _write_report(lines)
        print("PHASE79_SIGNAL_FREEZE_MISMATCH")
        return 2

    if not CANON.exists():
        lines += ["**Verdict:** `PHASE79_EXACT_SIGNAL_STREAM_UNAVAILABLE`", "", f"Missing {CANON}"]
        _write_report(lines)
        print("PHASE79_EXACT_SIGNAL_STREAM_UNAVAILABLE")
        return 2

    sh = config_hash()
    if sh != EXPECTED_SIGNAL_HASH:
        lines += [
            "**Verdict:** `PHASE79_EXACT_SIGNAL_STREAM_UNAVAILABLE`",
            "",
            f"Signal stream hash mismatch: expected {EXPECTED_SIGNAL_HASH} got {sh}",
        ]
        _write_report(lines)
        print("PHASE79_EXACT_SIGNAL_STREAM_UNAVAILABLE")
        return 2

    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()
    execs_sorted = execs.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(execs_sorted), 0.6, 0.8)

    baseline_trades, skipped = run_baseline_one_position(execs, m)
    baseline_trades = baseline_trades.merge(execs[["trade_id", "entry_ts"]], on="trade_id", how="left")
    repro_ok, repro_errs = verify_baseline_reproduction(execs, m, baseline_trades)
    if not repro_ok:
        lines += [
            "**Verdict:** `PHASE79_BASELINE_REPRODUCTION_FAIL`",
            "",
            "Errors:",
            *[f"- {e}" for e in repro_errs],
        ]
        _write_report(lines)
        _save_json("00_baseline_repro_fail.json", {"errors": repro_errs})
        print("PHASE79_BASELINE_REPRODUCTION_FAIL")
        return 2

    # Fixed entry set from baseline one-position (management must not re-filter entries)
    baseline_ids = set(baseline_trades["trade_id"])
    execs_fixed = execs[execs["trade_id"].isin(baseline_ids)].copy()

    atm_params = ATMParams(
        stop_r=ATM_A["stop_r"],
        target_r=ATM_A["target_r"],
        be_trigger_r=ATM_A["be_trigger_r"],
        be_offset_r=ATM_A["be_offset_r"],
        max_hold=ATM_A["max_hold_minutes"],
    )
    atm_trades = run_atm_on_entries(execs_fixed, m, atm_params)
    assert set(baseline_trades["trade_id"]) == set(atm_trades["trade_id"]), "trade_id mismatch"

    baseline_m = summarize(baseline_trades)
    atm_m = summarize(atm_trades)
    delta = compare(baseline_m, atm_m)

    trans = transition_table(baseline_trades, atm_trades)
    trans.to_csv(REPORTS / "TRANSITION_TABLE.csv", index=False)

    killed = killed_winners_analysis(baseline_trades, atm_trades)
    saved = saved_losers_analysis(baseline_trades, atm_trades)

    # Path-based killed-winner forensics on baseline TARGET trades
    base_targets = baseline_trades[baseline_trades["exit_reason"].isin(["M0_TARGET", "TARGET"])]
    path_killed = 0
    for _, row in base_targets.iterrows():
        ex = execs[execs["trade_id"] == row["trade_id"]].iloc[0]
        if counterfactual_killed_winner_path(
            m.hi, m.lo, m.cl, m.op,
            entry_i=int(ex["entry_i"]),
            direction=ex["direction"],
            entry_price=float(ex["entry_price"]),
            atr=float(ex["atr_entry"]),
            params=atm_params,
            n=m.n,
        ):
            path_killed += 1
    path_killed_stats = {
        "N_path_killed_winners": path_killed,
        "pct_baseline_targets": float(path_killed / len(base_targets)) if len(base_targets) else 0.0,
    }

    year_base = year_breakdown(baseline_trades)
    year_atm = year_breakdown(atm_trades)
    year_cmp = year_base.merge(year_atm, on="year", suffixes=("_base", "_atm"))
    year_cmp["DeltaAvgR"] = year_cmp["AvgR_atm"] - year_cmp["AvgR_base"]
    year_cmp["DeltaTotalR"] = year_cmp["TotalR_atm"] - year_cmp["TotalR_base"]
    year_cmp.to_csv(REPORTS / "YEAR_BREAKDOWN.csv", index=False)

    side_rows = []
    for direction in ("LONG", "SHORT"):
        b = summarize(baseline_trades[baseline_trades["direction"] == direction])
        a = summarize(atm_trades[atm_trades["direction"] == direction])
        side_rows.append({"direction": direction, **{f"baseline_{k}": v for k, v in b.items()}, **{f"atm_{k}": v for k, v in a.items()}, **{f"delta_{k}": compare(b, a)[k] for k in compare(b, a)}})
    side_df = pd.DataFrame(side_rows)
    side_df.to_csv(REPORTS / "LONG_SHORT_BREAKDOWN.csv", index=False)

    part_base = _partition_metrics(baseline_trades, execs_sorted, splits)
    part_atm = _partition_metrics(atm_trades, execs_sorted, splits)
    _save_json("03_partitions.json", {"baseline": part_base, "atm_a": part_atm})

    robustness_rows: list[dict] = []
    pass_gate, pass_fails = _evaluate_pass(baseline_m, atm_m, delta, year_cmp, None)

    if pass_gate:
        for trig in ROBUSTNESS_BE_TRIGGERS:
            for off in ROBUSTNESS_BE_OFFSETS:
                p = ATMParams(be_trigger_r=trig, be_offset_r=off)
                rt = run_atm_on_entries(execs_fixed, m, p)
                sm = summarize(rt)
                robustness_rows.append({"be_trigger_r": trig, "be_offset_r": off, **sm})
        pd.DataFrame(robustness_rows).to_csv(REPORTS / "ROBUSTNESS_NEIGHBORHOOD.csv", index=False)
        pass_gate, pass_fails = _evaluate_pass(baseline_m, atm_m, delta, year_cmp, robustness_rows)

    # Side viability
    for _, sr in side_df.iterrows():
        if sr["delta_DeltaAvgR"] <= 0:
            pass_gate = False
            pass_fails.append(f"{sr['direction']} AvgR did not improve")

    net_be_balance = saved["R_saved"] - killed["TotalR_damage"]
    verdict = "PHASE79_ATM_PASS" if pass_gate else "PHASE79_ATM_REJECT"

    _save_json("00_pine_freeze.json", {"pine_sha256": pine_hash, "ok": True})
    _save_json("01_signal_stream.json", {
        "signal_hash": sh,
        "source": str(CANON.relative_to(ROOT)),
        "pipeline": ENTRY_SPEC["pipeline"],
        "pine_reference": "TV_REVIEW/phase72a_autonomous_trader.pine",
        "N_signals": len(entries),
        "N_executed_one_position": len(baseline_trades),
        "skipped": skipped["N"],
    })
    _save_json("02_baseline_metrics.json", baseline_m)
    _save_json("03_atm_a_metrics.json", atm_m)
    _save_json("04_comparison.json", {**delta, "killed_winners": killed, "saved_losers": saved, "path_killed": path_killed_stats, "net_be_balance": net_be_balance})
    _save_json("18_final.json", {"verdict": verdict, "pass_fails": pass_fails})

    lines += [
        f"**Verdict:** `{verdict}`",
        "",
        "## Signal authority",
        f"- Pine SHA256: `{pine_hash}`",
        f"- Signal stream hash: `{sh}`",
        f"- Source: `{CANON.relative_to(ROOT)}`",
        f"- Date range: {entries['entry_ts'].min()} → {entries['entry_ts'].max()}",
        f"- Executed (one-position, current market data): {len(baseline_trades):,} (skipped {skipped['N']})",
        f"- Independent M0 anchor: N=36,174 AvgR=0.015992 (reproduced exactly)",
        f"- Note: Phase72 one-position N was 35,902; drift from extended OHLCV is documented, not a management change",
        "",
        "## Collision / causality policy",
        "- STOP_FIRST when stop and target on same bar (Phase73 M0 frozen policy)",
        "- BE trigger + BE stop same bar: activate BE if trigger reached without initial stop; then BE stop if low/high touches offset stop on same bar",
        "- No trailing before +1R; no partials; no future MFE/MAE for decisions",
        "",
        "## Comparison (net R, $14.50 RT cost)",
        "",
        "| Metric | BASELINE | ATM-A | Delta |",
        "|--------|----------|-------|-------|",
        f"| Trades | {baseline_m['N']:,} | {atm_m['N']:,} | — |",
        f"| Win Rate | {baseline_m['WinRate']:.3f} | {atm_m['WinRate']:.3f} | {atm_m['WinRate']-baseline_m['WinRate']:+.3f} |",
        f"| AvgR | {baseline_m['AvgR']:.4f} | {atm_m['AvgR']:.4f} | {delta['DeltaAvgR']:+.4f} |",
        f"| PF | {baseline_m['PF']:.3f} | {atm_m['PF']:.3f} | {delta['DeltaPF']:+.3f} |",
        f"| TotalR | {baseline_m['TotalR']:.1f} | {atm_m['TotalR']:.1f} | {delta['DeltaTotalR']:+.1f} |",
        f"| MaxDD | {baseline_m['MaxDD']:.1f} | {atm_m['MaxDD']:.1f} | {delta['DeltaMaxDD']:+.1f} |",
        f"| Median R | {baseline_m['MedianR']:.3f} | {atm_m['MedianR']:.3f} | {atm_m['MedianR']-baseline_m['MedianR']:+.3f} |",
        f"| Initial stops | {baseline_m.get('INITIAL_STOPS',0):,} | {atm_m.get('INITIAL_STOPS',0):,} | — |",
        f"| BE stops | {baseline_m.get('BE_STOPS',0):,} | {atm_m.get('BE_STOPS',0):,} | — |",
        f"| Targets | {baseline_m.get('TARGETS',0):,} | {atm_m.get('TARGETS',0):,} | — |",
        f"| Time exits | {baseline_m.get('TIME_EXITS',0):,} | {atm_m.get('TIME_EXITS',0):,} | — |",
        f"| Avg hold (min) | {baseline_m['AvgHold']:.1f} | {atm_m['AvgHold']:.1f} | — |",
        f"| Median hold | {baseline_m['MedianHold']:.1f} | {atm_m['MedianHold']:.1f} | — |",
        "",
        f"**BE activation rate:** {atm_m.get('BE_ACTIVATION_RATE', 0):.1%}",
        "",
        "## Breakeven attribution",
        f"- **ATM_SAVED_LOSERS:** N={saved['N']:,} ({saved['pct_of_baseline_losers']:.1%} of baseline stops), R saved={saved['R_saved']:.1f}",
        f"- **ATM_KILLED_WINNERS:** N={killed['N']:,} ({killed['pct_of_baseline_winners']:.1%} of baseline targets), R damage={killed['TotalR_damage']:.1f}",
        f"- **Path forensics (target trades hitting +1R then BE before 2.5R):** N={path_killed_stats['N_path_killed_winners']:,} ({path_killed_stats['pct_baseline_targets']:.1%})",
        f"- **Net R from BE rule:** saved − damage = **{net_be_balance:+.1f}**",
        "",
        "## Gross R",
        f"- Baseline gross AvgR: {baseline_m['GrossAvgR']:.4f} | ATM-A: {atm_m['GrossAvgR']:.4f} | Δ {delta['DeltaGrossAvgR']:+.4f}",
        "",
    ]
    if pass_fails:
        lines += ["## Pass gate failures", *[f"- {f}" for f in pass_fails], ""]
    if robustness_rows:
        lines += ["## Robustness neighborhood", "See `ROBUSTNESS_NEIGHBORHOOD.csv`", ""]
    lines += [f"Completed in {time.time()-t0:.1f}s"]
    _write_report(lines)

    baseline_trades.to_csv(REPORTS / "baseline_trades.csv", index=False)
    atm_trades.to_csv(REPORTS / "atm_a_trades.csv", index=False)

    print(verdict)
    print(f"Baseline AvgR={baseline_m['AvgR']:.4f} ATM-A AvgR={atm_m['AvgR']:.4f} Delta={delta['DeltaAvgR']:+.4f}")
    print(f"Killed winners={killed['N']} Saved losers={saved['N']} Net BE={net_be_balance:+.1f}")
    return 0 if verdict == "PHASE79_ATM_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
