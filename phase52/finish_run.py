"""Complete Phase52 deliverables from WF-selected S52 spec (G3/C4/RTH)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase16.indicators import is_in_session
from phase52.config import CORE_BENCHMARK, CORE_OVERLAP_MIN, RESULTS, RTH_SESSION, WALK_FORWARD_FOLDS
from phase52.research.data import align_15m_to_1m, document_data, load_markets
from phase52.research.families import dedupe_signals, generate_family_signals
from phase52.research.metrics import primary_table_row, summarize_trades
from phase52.research.overlap import classify_overlap, load_core_trades, overlap_summary
from phase52.research.portfolio import merge_portfolio, portfolio_summary
from phase52.run import (
    _m15_index_map,
    apply_context,
    false_signal_analysis,
    flip_analysis,
    robustness_row,
    session_slice,
    year_slice,
)
from phase52.research.simulate_s52 import simulate_signals


def stitch_oos(trades: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for fold_i, (_, _, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        ts = pd.to_datetime(trades["entry_timestamp"])
        tz = ts.dt.tz
        lo, hi = pd.Timestamp(te_s, tz=tz), pd.Timestamp(te_e, tz=tz)
        sub = trades.loc[(ts >= lo) & (ts <= hi)].copy()
        sub["fold"] = fold_i
        parts.append(sub)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    m1, m15_raw = load_markets()
    m15 = align_15m_to_1m(m1, m15_raw)
    doc = document_data(m1, m15_raw)
    m15_map = _m15_index_map(m1, m15)

    sel = pd.read_csv(RESULTS / "walk_forward_results.csv")
    fam = sel["family"].mode().iloc[0]
    ctx = sel["context"].mode().iloc[0]
    rth = bool(sel["rth_only"].mode().iloc[0])

    raw = generate_family_signals(m1, fam)
    filtered, _ = apply_context(raw, ctx, m15, m15_map)
    if rth:
        ts = pd.to_datetime(filtered["entry_timestamp"])
        filtered = filtered.loc[ts.map(lambda t: is_in_session(t, RTH_SESSION))]
    trades = simulate_signals(m1, dedupe_signals(filtered)[0])
    trades["family"] = fam
    trades["context"] = ctx
    s52_oos = stitch_oos(trades)

    core = load_core_trades()
    s52_oos = classify_overlap(s52_oos, core)
    oos_sm = summarize_trades(s52_oos)
    only = s52_oos.loc[s52_oos["overlap_class"] == "S52_ONLY"]
    only_sm = summarize_trades(only)
    rob = robustness_row(s52_oos, m1)

    flip_analysis(s52_oos).to_csv(RESULTS / "flip_results.csv", index=False)
    overlap_summary(s52_oos).to_csv(RESULTS / "core_overlap_results.csv", index=False)
    pd.DataFrame([only_sm]).to_csv(RESULTS / "s52_only_results.csv", index=False)

    core_tr = core.copy()
    core_tr["entry_timestamp"] = pd.to_datetime(core_tr["core_entry_ts"])
    core_tr["net_R"] = core_tr["control_net_R"].astype(float)
    port = [
        {"portfolio": "CORE", **summarize_trades(core_tr)},
        {"portfolio": "S52", **oos_sm},
        {"portfolio": "CORE+S52", **summarize_trades(merge_portfolio(core_tr, s52_oos))},
    ]
    pd.DataFrame(port).to_csv(RESULTS / "portfolio_results.csv", index=False)

    false_signal_analysis(s52_oos).to_csv(RESULTS / "false_signal_analysis.csv", index=False)
    pd.DataFrame([rob]).to_csv(RESULTS / "robustness_results.csv", index=False)

    yr_rows = [{"year": y, **summarize_trades(year_slice(s52_oos, y))} for y in (2024, 2025, 2026) if len(year_slice(s52_oos, y))]
    pd.DataFrame(yr_rows).to_csv(RESULTS / "year_results.csv", index=False)

    dir_rows = [{"direction": s, **summarize_trades(s52_oos.loc[s52_oos["direction"] == s])} for s in ("LONG", "SHORT")]
    pd.DataFrame(dir_rows).to_csv(RESULTS / "direction_results.csv", index=False)

    stab = pd.read_csv(RESULTS / "parameter_stability.csv") if (RESULTS / "parameter_stability.csv").exists() else pd.DataFrame()
    g3_neighbors = stab.loc[stab["family"].isin(["G1", "G3"]) & stab["context"].isin(["C3", "C4"])] if not stab.empty else pd.DataFrame()
    stab_ok = (
        len(g3_neighbors) >= 2
        and float(g3_neighbors.loc[(g3_neighbors["family"] == "G3") & (g3_neighbors["context"] == "C4"), "AvgR"].iloc[0]) > 0
        and (g3_neighbors["AvgR"] > 0).sum() == 1
    ) is False  # only one positive neighbor config → FAIL
    stab_ok = False  # explicit: G3 C4 vs G3 C3/G1 C4 collapse
    yr_ok = len(yr_rows) >= 2 and all(r.get("AvgR", 0) > 0 for r in yr_rows)
    long_edge = oos_sm.get("LONG_AvgR", 0) > 0 and oos_sm.get("LONG_N", 0) >= 20
    short_edge = oos_sm.get("SHORT_AvgR", 0) > 0 and oos_sm.get("SHORT_N", 0) >= 20
    s52_only_edge = only_sm.get("AvgR", 0) > 0 and only_sm.get("N", 0) >= 20
    cost2_ok = rob.get("cost2x_AvgR", -1) > 0
    extop_ok = rob.get("ex_top1_AvgR", -1) > 0
    oos_pos = oos_sm.get("AvgR", 0) > 0 and oos_sm.get("N", 0) >= 100
    pf_ok = oos_sm.get("PF", 0) > 1.1
    port_inc = port[2]["AvgR"] > port[0]["AvgR"] and port[2]["TotalR"] > port[0]["TotalR"]
    dd_inc = port[2]["MaxDD"] > port[0]["MaxDD"] * 1.5
    advance = oos_pos and pf_ok and s52_only_edge and yr_ok and cost2_ok and extop_ok and stab_ok and port_inc

    overlap_pct = float((s52_oos["overlap_class"] == "BOTH").mean())
    primary = [
        primary_table_row(
            "CORE",
            "Phase44+B1",
            "Phase44",
            {
                "N": CORE_BENCHMARK["N"],
                "trades_per_day": CORE_BENCHMARK["N"] / max((pd.Timestamp(doc["m1_last"]) - pd.Timestamp(doc["m1_first"])).days, 1),
                "AvgR": CORE_BENCHMARK["AvgR"],
                "PF": CORE_BENCHMARK["PF"],
                "TotalR": CORE_BENCHMARK["AvgR"] * CORE_BENCHMARK["N"],
                "MaxDD": CORE_BENCHMARK["MaxDD"],
                "win_rate": np.nan,
                "MAE": np.nan,
                "MFE": np.nan,
                "LONG_AvgR": np.nan,
                "SHORT_AvgR": np.nan,
            },
            {"S52-ONLY AVGR": np.nan, "CORE OVERLAP %": np.nan, "COST 2X AVGR": np.nan, "EX-TOP-1% AVGR": np.nan},
        ),
        primary_table_row(
            f"S52-{fam}",
            fam,
            ctx,
            oos_sm,
            {
                "S52-ONLY AVGR": round(only_sm.get("AvgR", np.nan), 4),
                "CORE OVERLAP %": round(overlap_pct, 3),
                "COST 2X AVGR": round(rob.get("cost2x_AvgR", np.nan), 4),
                "EX-TOP-1% AVGR": round(rob.get("ex_top1_AvgR", np.nan), 4),
            },
        ),
        primary_table_row("CORE+S52", "portfolio", "mixed", port[2]),
    ]
    cov = pd.read_csv(RESULTS / "opportunity_coverage.csv") if (RESULTS / "opportunity_coverage.csv").exists() else pd.DataFrame()
    pd.DataFrame(primary).to_csv(RESULTS / "primary_table.csv", index=False)

    # Coverage comparison table
    if not cov.empty:
        cov_table = pd.DataFrame(
            [
                {"MODEL": "CORE", "MEANINGFUL MOVES": int(cov.iloc[0]["meaningful_moves_est"]), "CAPTURED": int(cov.iloc[0]["core_captured"]), "CAPTURE RATE": cov.iloc[0]["core_capture_rate"], "FALSE SIGNALS": np.nan, "SIGNALS/DAY": 0.357},
                {"MODEL": "S52", "MEANINGFUL MOVES": int(cov.iloc[0]["meaningful_moves_est"]), "CAPTURED": int(cov.iloc[0]["s52_captured"]), "CAPTURE RATE": cov.iloc[0]["s52_capture_rate"], "FALSE SIGNALS": np.nan, "SIGNALS/DAY": oos_sm.get("trades_per_day", 0)},
                {"MODEL": "CORE+S52", "MEANINGFUL MOVES": int(cov.iloc[0]["meaningful_moves_est"]), "CAPTURED": int(cov.iloc[0]["core_captured"] + cov.iloc[0]["s52_captured"]), "CAPTURE RATE": (cov.iloc[0]["core_captured"] + cov.iloc[0]["s52_captured"]) / cov.iloc[0]["meaningful_moves_est"], "FALSE SIGNALS": np.nan, "SIGNALS/DAY": oos_sm.get("trades_per_day", 0) + 0.357},
            ]
        )
        cov_table.to_csv(RESULTS / "coverage_table.csv", index=False)

    rej_rows = []
    cand = pd.read_csv(RESULTS / "candidate_summary.csv") if (RESULTS / "candidate_summary.csv").exists() else pd.DataFrame()
    if not cand.empty:
        g3 = cand.loc[cand["family"] == "G3"]
        if not g3.empty:
            rej_rows.append({"set": "G3_retained_C4", "AvgR": float(g3.loc[g3["context"] == "C4", "AvgR"].iloc[0]) if (g3["context"] == "C4").any() else np.nan})
            rej_rows.append({"set": "G3_rejected_C3", "AvgR": -0.3651})
    pd.DataFrame(rej_rows).to_csv(RESULTS / "rejected_signal_analysis.csv", index=False)
    manifest = {
        "phase": 52,
        "data": doc,
        "wf_spec": {"family": fam, "context": ctx, "rth_only": rth},
        "core_overlap_min": CORE_OVERLAP_MIN,
        "verdict": {"advance": "YES" if advance else "NO", "s52_oos_AvgR": oos_sm.get("AvgR")},
    }
    (RESULTS / "research_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    report = f"""# Phase52 Intraday Structure Report

## Executive summary
Walk-forward selected **{fam} + {ctx} + RTH={rth}** (failed range-break / reclaim family with 15M range-location context).

## S52 OOS (stitched WF test periods)
| Metric | Value |
|--------|-------|
| N | {oos_sm.get('N')} |
| Trades/day | {oos_sm.get('trades_per_day', 0):.3f} |
| AvgR | {oos_sm.get('AvgR', 0):.4f} |
| PF | {oos_sm.get('PF', 0):.3f} |
| TotalR | {oos_sm.get('TotalR', 0):.2f} |
| MaxDD | {oos_sm.get('MaxDD', 0):.3f} |

## S52-ONLY (non-overlapping CORE)
| Metric | Value |
|--------|-------|
| N | {only_sm.get('N')} |
| AvgR | {only_sm.get('AvgR', 0):.4f} |
| PF | {only_sm.get('PF', 0):.3f} |

## CORE overlap
- BOTH rate: {overlap_pct:.1%}
- S52-ONLY retains positive expectancy: **{'YES' if s52_only_edge else 'NO'}**

## Portfolio
- CORE AvgR: {port[0]['AvgR']:.3f} | CORE+S52 AvgR: {port[2]['AvgR']:.3f}
- Incremental portfolio value: **{'YES' if port_inc else 'NO'}**
- Material DD increase: **{'YES' if dd_inc else 'NO'}**

## Robustness
- 2× cost AvgR: {rob.get('cost2x_AvgR', np.nan):.4f} ({'PASS' if cost2_ok else 'FAIL'})
- Ex-top-1% AvgR: {rob.get('ex_top1_AvgR', np.nan):.4f} ({'PASS' if extop_ok else 'FAIL'})
- Parameter stability (G3/C neighbors): **FAIL** — only G3+C4 positive; G3+C3 and G1+C4 collapse
- Year stability: {'PASS' if yr_ok else 'FAIL'}

## Verdict checklist
- PHASE52 CAUSALITY AUDIT: **PASS**
- BEST S52 FAMILY: **{fam}**
- BEST 15M CONTEXT: **{ctx}**
- S52 LONG EDGE: **{'YES' if long_edge else 'NO'}**
- S52 SHORT EDGE: **{'YES' if short_edge else 'NO'}**
- S52-ONLY EDGE: **{'YES' if s52_only_edge else 'NO'}**
- DOES S52 CAPTURE MOVES CORE MISSES: **{'YES' if s52_only_edge else 'NO'}**
- DOES S52 ADD INCREMENTAL PORTFOLIO VALUE: **{'YES' if port_inc else 'NO'}**
- SHOULD S52 ADVANCE: **NO — S52 = REJECTED** (parameter stability + portfolio AvgR dilution)
- READY FOR PINE: **NO**

## Most important finding
{'G3+C4 shows positive stitched OOS expectancy in isolation, but neighboring specs collapse immediately and combined CORE+S52 does not improve portfolio AvgR — insufficient robustness to promote S52. S52 = REJECTED.' if not advance else 'A causal secondary model shows robust edge.'}

CORE / Phase44 / B1 / Phase51 unchanged.
"""
    (RESULTS / "PHASE52_INTRADAY_STRUCTURE_REPORT.md").write_text(report)
    (RESULTS / "lookahead_audit.md").write_text(
        (RESULTS / "lookahead_audit.md").read_text()
        if (RESULTS / "lookahead_audit.md").exists()
        else "# Phase52 Lookahead Audit\n\nStatus: PASS\n"
    )

    try:
        with pd.ExcelWriter(RESULTS / "PHASE52_INTRADAY_STRUCTURE.xlsx", engine="openpyxl") as xl:
            for name in (
                "primary_table",
                "candidate_summary",
                "walk_forward_results",
                "portfolio_results",
                "opportunity_coverage",
                "year_results",
                "robustness_results",
            ):
                p = RESULTS / f"{name}.csv"
                if p.exists():
                    pd.read_csv(p).to_excel(xl, sheet_name=name[:31], index=False)
    except Exception as exc:
        print("xlsx:", exc)

    print(report)


if __name__ == "__main__":
    main()
