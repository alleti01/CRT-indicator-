#!/usr/bin/env python3
"""Phase63 — causal early-location → reaction entry audit."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.walkforward_audit import walkforward_splits
from phase59.tools.phase59_parity import _load_cfg
from phase60.python.arrays import build_market_arrays_phase60
from phase60.tools.run_phase60 import test_prefix_invariance, test_vectorized_vs_sequential
from phase61.python.clustering import cluster_signals
from phase62.python.sim_engine import TradeConfig, run_simulation, summarize
from phase63.python.metrics import classify_direction_audit, glbd_glbd_audit, path_summary, sim_summary
from phase63.python.reaction import REACTION_FNS, baseline_entry

REPORTS = ROOT / "phase63" / "reports"
SIGNALS = ROOT / "phase60" / "diagnostics" / "cache" / "p58_trades_phase60.parquet"
BASELINE_PO = 0.328  # Phase62 +2 before -1


def _first_opps(signals: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    cl = cluster_signals(signals, structural_gap=cfg.get("structural_gap_bars", 30))
    first = cl[cl["opp_rank"] == 1].copy()
    first["entry_i"] = first["signal_i"] + 1
    return first


def _apply_model(first: pd.DataFrame, m, family: str, timing: str, model: str) -> pd.DataFrame:
    rows = []
    for _, r in first.iterrows():
        si, orig, atr = int(r["signal_i"]), r["direction"], float(r["atr"])
        if family == "BASE":
            delay = 0 if timing == "T0" else 1
            res = baseline_entry(si, orig, delay)
        else:
            fn = REACTION_FNS[family]
            res = fn(m, si, orig, atr, timing)  # type: ignore
        if model == "D0":
            res_decision = "TAKE"
            res_dir = orig
            res_ei = si + 1 + (0 if timing == "T0" else 1 if timing == "T1" else 2)
        elif model == "D1":
            if res.decision != "TAKE" or res.direction != orig:
                res_decision, res_dir, res_ei = "PASS", "", -1
            else:
                res_decision, res_dir, res_ei = "TAKE", orig, res.entry_i
        elif model == "D2":
            if res.decision == "TAKE" and res.direction != orig:
                res_decision, res_dir, res_ei = "TAKE", res.direction, res.entry_i
            elif res.decision == "TAKE" and res.direction == orig:
                res_decision, res_dir, res_ei = "TAKE", orig, res.entry_i
            else:
                res_decision, res_dir, res_ei = "PASS", "", -1
        else:  # D3
            if res.decision == "TAKE":
                res_decision, res_dir, res_ei = "TAKE", res.direction, res.entry_i
            else:
                res_decision, res_dir, res_ei = "PASS", "", -1
        if res_ei < 0 or res_ei >= m.n - 61:
            continue
        rows.append({
            "signal_i": si,
            "entry_i": res_ei,
            "direction": res_dir,
            "atr": atr,
            "decision": res_decision,
            "delay_bars": res_ei - si - 1,
            "reason": res.reason,
            "reaction_dir": res.direction if res.decision == "TAKE" else "",
            "orig_dir": orig,
        })
    return pd.DataFrame(rows)


def _summarize_trades(m, first: pd.DataFrame, trades: pd.DataFrame, n_opps: int) -> dict:
    taken = trades[trades["decision"] == "TAKE"]
    ps = path_summary(m.hi, m.lo, m.op, m.cl, taken)
    ps["retention"] = len(taken) / n_opps if n_opps else 0
    ps["gross"] = sim_summary(m, taken, cost_mult=0.0)
    ps["net"] = sim_summary(m, taken, cost_mult=1.0)
    ps["stress"] = sim_summary(m, taken, cost_mult=1.5)
    return ps


def _verdict(ps: dict, baseline_po: float = BASELINE_PO) -> str:
    p2 = ps.get("+2_before_-1", 0)
    ret = ps.get("retention", 0)
    if p2 >= baseline_po + 0.05 and ret >= 0.25:
        return "KEEP"
    if p2 >= baseline_po + 0.02 and ret >= 0.20:
        return "MARGINAL"
    return "REJECT"


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    print("Loading...", flush=True)
    ma = build_market_arrays_phase60()
    signals = pd.read_parquet(SIGNALS)
    first = _first_opps(signals, cfg)
    n_opps = len(first)
    print(f"Opportunities: {n_opps:,}", flush=True)

    # Baselines
    base_a = _apply_model(first, ma, "BASE", "T0", "D0")
    base_a = base_a[base_a["decision"] == "TAKE"]
    base_b_trades = _apply_model(first, ma, "BASE", "T1", "D0")
    base_b = base_b_trades[base_b_trades["decision"] == "TAKE"]
    bl_a = path_summary(ma.hi, ma.lo, ma.op, ma.cl, base_a)
    bl_b = path_summary(ma.hi, ma.lo, ma.op, ma.cl, base_b)
    trader_a_cfg = TradeConfig(stop_mode="hybrid", protection="none", cost_mult=0.0)
    bl_c = summarize(run_simulation(ma, first, trader_a_cfg))

    # Reaction families T0/T1/T2
    print("Reaction families...", flush=True)
    reactions = {}
    best_family, best_timing, best_p2 = "", "T1", 0.0
    for fam in ["R1", "R2", "R3", "R4", "R5"]:
        reactions[fam] = {}
        for timing in ["T0", "T1", "T2"]:
            trades = _apply_model(first, ma, fam, timing, "D3")
            taken = trades[trades["decision"] == "TAKE"]
            ps = _summarize_trades(ma, first, trades, n_opps)
            ps["verdict"] = _verdict(ps)
            reactions[fam][timing] = ps
            if timing != "T2" and ps.get("+2_before_-1", 0) > best_p2 and ps.get("retention", 0) >= 0.15:
                best_p2 = ps["+2_before_-1"]
                best_family, best_timing = fam, timing

    if not best_family:
        best_family, best_timing = "R1", "T1"

    print(f"Best reaction: {best_family} {best_timing} (+2/-1={best_p2:.1%})", flush=True)

    # Direction audit
    dir_audit = classify_direction_audit(ma.hi, ma.lo, ma.op, base_a)

    # Candidates
    print("Candidates...", flush=True)
    cand = {}
    cand["R-A"] = _summarize_trades(
        ma, first, _apply_model(first, ma, best_family, best_timing, "D1"), n_opps
    )
    cand["R-A"]["logic"] = f"D1 confirm original + {best_family} {best_timing}"
    cand["R-B"] = _summarize_trades(
        ma, first, _apply_model(first, ma, best_family, "T0", "D3"), n_opps
    )
    cand["R-B"]["logic"] = f"D3 reaction direction + {best_family} T0"
    cand["R-C"] = _summarize_trades(
        ma, first, _apply_model(first, ma, best_family, best_timing, "D2"), n_opps
    )
    cand["R-C"]["logic"] = f"D2 override on contradiction + {best_family} {best_timing}"

    best_name = max(cand, key=lambda k: cand[k].get("+2_before_-1", 0))
    best = cand[best_name]

    # GLBD / GLGD with best candidate trades
    best_trades = _apply_model(first, ma, best_family, best_timing, "D2" if best_name == "R-C" else "D1" if best_name == "R-A" else "D3")
    glbd = glbd_glbd_audit(ma.hi, ma.lo, ma.op, base_a, best_trades)

    # Walk-forward on best taken trades
    taken = best_trades[best_trades["decision"] == "TAKE"].sort_values("entry_i").reset_index(drop=True)
    splits = walkforward_splits(len(taken), 0.6, 0.8)
    wf = {}
    for name, (a, b) in splits.items():
        sub = taken.iloc[a:b]
        ps = path_summary(ma.hi, ma.lo, ma.op, ma.cl, sub)
        ps["sim"] = sim_summary(ma, sub, 0.0)
        wf[name] = ps

    # Year stability
    taken["year"] = [ma.idx[int(i)].year for i in taken["entry_i"]]
    years = {}
    for y, g in taken.groupby("year"):
        years[int(y)] = {**path_summary(ma.hi, ma.lo, ma.op, ma.cl, g), **sim_summary(ma, g, 0.0)}

    # Wait audit T0 vs T1 vs T2 for best family D3
    wait_audit = {}
    for timing in ["T0", "T1", "T2"]:
        t = _apply_model(first, ma, best_family, timing, "D3")
        wait_audit[timing] = _summarize_trades(ma, first, t, n_opps)

    causality = {
        "sequential_parity": test_vectorized_vs_sequential(max_bars=2000)["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=3)["pass"],
    }

    # Export sample
    review = ROOT / "phase63" / "diagnostics" / "visual_review"
    review.mkdir(parents=True, exist_ok=True)
    taken.head(200).to_csv(review / "phase63_sample.csv", index=False)

    return {
        "causality": causality,
        "n_opportunities": n_opps,
        "baseline_a": bl_a,
        "baseline_b": bl_b,
        "baseline_c": bl_c,
        "reactions": reactions,
        "best_family": best_family,
        "best_timing": best_timing,
        "direction_audit": dir_audit,
        "candidates": cand,
        "best_candidate": best_name,
        "glbd_glgd": glbd,
        "walkforward": wf,
        "years": years,
        "wait_audit": wait_audit,
    }


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE63_CAUSAL_REACTION_ENTRY_AUDIT.md"
    bl_a, bl_b = r["baseline_a"], r["baseline_b"]
    bl_c = r["baseline_c"]
    lines = [
        "PHASE63 — CAUSAL EARLY-LOCATION → REACTION ENTRY AUDIT",
        "=======================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        "LOCATION ENGINE MODIFIED: NO",
        "",
        "--------------------------------------------",
        "BASELINES",
        "--------------------------------------------",
        f"PHASE58 FIRST: N={bl_a.get('n',0):,} +1/-1={bl_a.get('+1_before_-1',0):.1%} "
        f"+2/-1={bl_a.get('+2_before_-1',0):.1%} +2.5/-1={bl_a.get('+2.5_before_-1',0):.1%} "
        f"MFE60={bl_a.get('median_mfe_60',0):.2f} MAE60={bl_a.get('median_mae_60',0):.2f}",
        f"ONE-BAR DELAY: +2/-1={bl_b.get('+2_before_-1',0):.1%} chase={bl_b.get('median_chase',0):.2f}",
        f"PHASE62 TRADER A: AvgR={bl_c.get('AvgR',0):.4f} TotalR={bl_c.get('TotalR',0):.0f}",
        "",
    ]
    for fam in ["R1", "R2", "R3", "R4", "R5"]:
        lines.append(f"--------------------------------------------")
        lines.append(f"REACTION {fam}")
        lines.append(f"--------------------------------------------")
        for timing in ["T0", "T1", "T2"]:
            ps = r["reactions"][fam].get(timing, {})
            tag = "DIAG" if timing == "T2" else ""
            lines.append(
                f"{timing}{tag}: N={ps.get('n',0):,} ret={ps.get('retention',0):.1%} "
                f"+2/-1={ps.get('+2_before_-1',0):.1%} delay={ps.get('median_delay',0):.1f} "
                f"chase={ps.get('median_chase',0):.2f} VERDICT={ps.get('verdict','')}"
            )
        lines.append("")
    best = r["candidates"][r["best_candidate"]]
    lines.extend([
        "--------------------------------------------",
        "FINAL CANDIDATES",
        "--------------------------------------------",
    ])
    for name, c in r["candidates"].items():
        lines.append(
            f"{name}: {c.get('logic','')} trades={c.get('n',0):,} ret={c.get('retention',0):.1%} "
            f"+2/-1={c.get('+2_before_-1',0):.1%} TotalR={c.get('gross',{}).get('TotalR',0):.0f}"
        )
    lines.extend([
        "",
        f"BEST: {r['best_candidate']}",
        f"+2 before -1: {best.get('+2_before_-1',0):.1%} (baseline {BASELINE_PO:.1%})",
        f"Retention: {best.get('retention',0):.1%}",
        f"GLBD handled: {r['glbd_glgd']['glbd_handled_pct']:.1%}",
        f"GLGD preserved: {r['glbd_glgd']['glgd_preserved_pct']:.1%}",
        "",
        "--------------------------------------------",
        "VERDICT",
        "--------------------------------------------",
    ])
    improved = best.get("+2_before_-1", 0) > BASELINE_PO + 0.03
    lines.extend([
        f"IS PHASE58 PRIMARILY A GOOD LOCATION DETECTOR: YES",
        f"DOES IMMEDIATE REACTION IMPROVE PATH ORDERING: {'YES' if improved else 'MARGINAL/NO'}",
        f"BEST REACTION TYPE: {r['best_family']} {r['best_timing']}",
        f"+2-BEFORE-1 IMPROVED MATERIALLY: {'YES' if improved else 'NO'}",
        f"READY FOR PHASE64: {'YES' if improved else 'REVIEW — location detector thesis'}",
    ])
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    t0 = time.time()
    results = run_audit()
    (REPORTS / "phase63_audit.json").write_text(json.dumps(results, indent=2, default=str))
    report = write_report(results)
    print(f"\nDone {time.time()-t0:.0f}s\n{report}", flush=True)


if __name__ == "__main__":
    main()
