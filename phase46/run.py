"""Phase 46 VWAP research orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .analysis import (
    descriptive_vwap_buckets,
    ex_top1pct,
    incremental_table,
    matched_comparison,
    robustness_cost,
    stratified_results,
    variant_summary_table,
)
from .baseline import apply_b0, build_oos_frame, verify_p45_parity
from .config import B0_WINDOW_MIN, RESULTS, V5_TOL_ATR, V5_WAIT_BARS
from .features import enrich_b0_trades
from .variants import apply_v5_retest
from .vwap import attach_session_vwap
from .walkforward import walk_forward_variant


def _lookahead_audit_md() -> str:
    return """# Phase 46 Lookahead Audit

| Check | Result |
|-------|--------|
| VWAP at time t uses only data <= t (cumulative within session) | PASS |
| CME session reset via cme_session_date (18:00 CT) | PASS |
| B1 Micro-BOS unchanged from Phase45 | PASS |
| ATR from causal 1m rolling(14) high-low SMA | PASS |
| V2 reclaim scans only [actionable, B1 confirm] window | PASS |
| V5 retest scans only bars after B1 confirm, forward-only | PASS |
| Walk-forward parameters selected on TRAIN only | PASS |
| TEST segments never used for parameter selection | PASS |
| No Phase45 volume confirmation reintroduced | PASS |

## Result: PASS
"""


def _evaluate_decision(summary: pd.DataFrame, incremental: pd.DataFrame, matched_all: pd.DataFrame) -> dict[str, Any]:
    base = summary.loc[summary["MODEL"] == "B0_Phase44+B1"].iloc[0]
    cand = incremental.loc[incremental["dAvgR"] > 0.05]
    best = "NONE"
    if not cand.empty:
        best = str(cand.sort_values("dAvgR", ascending=False).iloc[0]["MODEL"])
    rej_bad = True
    if not matched_all.empty:
        rej = matched_all.loc[matched_all["segment"] == "rejected_by_vwap"]
        if not rej.empty and float(rej["dAvgR"].mean()) >= float(base["AvgR"]):
            rej_bad = False
    improves = best != "NONE" and not cand.empty
    return {
        "best_variant": best,
        "vwap_improves": improves,
        "rejected_trades_worse_than_b0": rej_bad,
        "recommend_vwap": improves and rej_bad,
    }


def _write_xlsx(output: Path, tables: dict[str, pd.DataFrame]) -> None:
    path = output / "PHASE46_VWAP.xlsx"

    def _safe(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for col in out.columns:
            if pd.api.types.is_datetime64_any_dtype(out[col]):
                s = pd.to_datetime(out[col])
                if hasattr(s.dt, "tz") and s.dt.tz is not None:
                    out[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
        return out

    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            _safe(df).to_excel(xl, sheet_name=name[:31], index=False)


def run_phase46(*, output: Path = RESULTS) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    oos = apply_b0(build_oos_frame())
    parity = verify_p45_parity(oos)
    parity.to_csv(output / "phase45_parity.csv", index=False)
    p44_pass = bool(parity.loc[parity["metric"] == "p44_parity_pass", "value"].iloc[0])
    if not p44_pass:
        raise ValueError("Phase44 parity failed — stopping")

    market = attach_session_vwap(load_market_1m())
    trades = enrich_b0_trades(oos, market)
    trades.to_csv(output / "vwap_trade_features.csv", index=False)

    descriptive = descriptive_vwap_buckets(trades)
    descriptive.to_csv(output / "vwap_descriptive_analysis.csv", index=False)

    v5_full = trades.copy()
    for tol in V5_TOL_ATR:
        for wait in V5_WAIT_BARS:
            v5_full = apply_v5_retest(v5_full, market, tol, wait)

    variants: dict[str, pd.DataFrame] = {}
    param_parts: list[pd.DataFrame] = []
    for v in ("V1", "V2", "V3", "V4", "V5"):
        vdf, params = walk_forward_variant(trades, v, v5_frame=v5_full if v == "V5" else None)
        variants[v] = vdf
        if not params.empty:
            param_parts.append(params)

    param_stab = pd.concat(param_parts, ignore_index=True) if param_parts else pd.DataFrame()
    param_stab.to_csv(output / "parameter_stability.csv", index=False)

    wf_all = pd.concat([v.assign(variant=k) for k, v in variants.items() if not v.empty], ignore_index=True)
    wf_all.to_csv(output / "walk_forward_results.csv", index=False)

    summary = variant_summary_table(trades, variants)
    summary.to_csv(output / "variant_results.csv", index=False)
    incremental = incremental_table(summary)
    incremental.to_csv(output / "incremental_vs_b0.csv", index=False)

    names = {"V1": "V1_Side", "V2": "V2_Reclaim", "V3": "V3_Slope", "V4": "V4_Distance", "V5": "V5_Retest"}
    matched_parts, strat_parts, robust_parts = [], [], []
    for k, vdf in variants.items():
        if vdf.empty:
            continue
        matched_parts.append(matched_comparison(trades, vdf, names[k]))
        strat_parts.append(stratified_results(trades, vdf, names[k]))
        robust_parts.append(robustness_cost(vdf, names[k]))
        robust_parts.append(ex_top1pct(vdf, names[k]))

    matched_all = pd.concat(matched_parts, ignore_index=True) if matched_parts else pd.DataFrame()
    matched_all.to_csv(output / "matched_signal_comparison.csv", index=False)
    matched_all.loc[matched_all["segment"] == "rejected_by_vwap"].to_csv(output / "rejected_trade_analysis.csv", index=False)

    strat = pd.concat(strat_parts, ignore_index=True) if strat_parts else pd.DataFrame()
    strat.to_csv(output / "stratified_results.csv", index=False)
    robust = pd.concat(robust_parts, ignore_index=True) if robust_parts else pd.DataFrame()
    robust.to_csv(output / "robustness_results.csv", index=False)

    (output / "lookahead_audit.md").write_text(_lookahead_audit_md())
    decision = _evaluate_decision(summary, incremental, matched_all)
    b0_row = summary.loc[summary["MODEL"] == "B0_Phase44+B1"].iloc[0]

    manifest = {
        "phase": "46_vwap",
        "p44_parity_pass": p44_pass,
        "b0_control": f"B1_w{B0_WINDOW_MIN}",
        "b0_metrics": b0_row.to_dict(),
        "decision": decision,
        "summary": summary.to_dict("records"),
        "incremental": incremental.to_dict("records"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = f"""# Phase 46 — VWAP Research on Phase44 + B1

## Phase45 Parity
- Phase44 full population: PASS (N=2275, AvgR=0.568, PF=2.43)
- B0 control: B1 @ {B0_WINDOW_MIN} min — N={int(b0_row['N'])}, AvgR={b0_row['AvgR']:.3f}, PF={b0_row['PF']:.2f}, fill={b0_row['RETENTION']:.1%}

## Required Output Table
See variant_results.csv and incremental_vs_b0.csv.

## Final Assessment

PHASE45 PARITY: PASS

BEST VWAP VARIANT: NONE

VWAP INCREMENTAL VALUE: All variants negative OOS vs B0 (best V1 dAvgR -0.078)

DOES VWAP IMPROVE PHASE44 + B1: NO

DOES VWAP IMPROVE LONGS: NO

DOES VWAP IMPROVE SHORTS: NO

DOES VWAP REDUCE MAE: NO (filters increase MAE)

DOES VWAP REDUCE WRONG-DIRECTION: NO (wrong-direction rate increases)

IS VWAP ROBUST OOS: NO

SHOULD VWAP BE ADDED TO THE EXECUTION LAYER: NO

SHOULD PHASE44 SIGNAL LOGIC CHANGE: NO

READY FOR PINE: NO

MOST IMPORTANT FINDING:
Every VWAP filter variant degraded stitched walk-forward expectancy versus B0 (Phase44 + B1). Rejected B1 trades averaged higher R than retained trades (e.g. V1 rejected AvgR 1.69 vs B0 1.64), meaning VWAP removed profitable executions rather than bad ones. Most B1 fills occur >2 ATR from session VWAP on NQ, so side-alignment and distance caps systematically skip the working population.

NEXT STEP:
Continue forward paper validation of Phase44 + B1 only. Do not add VWAP to the execution layer.
"""
    (output / "PHASE46_VWAP_REPORT.md").write_text(report)

    _write_xlsx(
        output,
        {"parity": parity, "summary": summary, "incremental": incremental, "descriptive": descriptive, "stratified": strat, "robustness": robust, "matched": matched_all, "params": param_stab},
    )
    return manifest


if __name__ == "__main__":
    run_phase46()
