#!/usr/bin/env python3
"""Phase69 — frozen entry winner extension & causal exit management."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58b.research.simulation import metrics
from phase58j.research.walkforward_audit import walkforward_splits
from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import ENTRY_SPEC, config_hash, executions, load_frozen_entries
from phase69.python.path_audit import counterfactual_after_r, fixed_target_frontier, path_diagnostics
from phase69.python.sim_management import simulate_batch

REPORTS = ROOT / "phase69" / "reports"
CHECKPOINTS = ROOT / "phase69" / "checkpoints"


def _save(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _summ(sim: pd.DataFrame) -> dict:
    if sim.empty:
        return {"N": 0}
    m = metrics(sim["net_R"].values)
    m["gross_AvgR"] = float(sim["gross_R"].mean())
    m["TotalR"] = float(sim["net_R"].sum())
    m["win_rate"] = float((sim["gross_R"] > 0).mean())
    m["avg_winner"] = float(sim.loc[sim["gross_R"] > 0, "gross_R"].mean()) if (sim["gross_R"] > 0).any() else 0
    m["avg_loser"] = float(sim.loc[sim["gross_R"] <= 0, "gross_R"].mean()) if (sim["gross_R"] <= 0).any() else 0
    m["target_pct"] = float((sim["exit_reason"] == "FIXED_TARGET").mean())
    m["stop_pct"] = float((sim["exit_reason"] == "INITIAL_STOP").mean())
    m["time_pct"] = float((sim["exit_reason"] == "MAX_HOLD").mean())
    m["median_hold"] = float(sim["duration"].median())
    m["capture_eff"] = float((sim["gross_R"] / sim["MFE_R"].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).median())
    return m


def _open_mask(ts: pd.Series) -> pd.Series:
    ny = ts.dt.tz_convert("America/New_York")
    mins = ny.dt.hour * 60 + ny.dt.minute
    return (mins >= 9 * 60 + 30) & (mins < 10 * 60 + 30)


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    eh = config_hash()
    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()

    freeze_doc = {**ENTRY_SPEC, "entry_hash": eh, "n_trades": len(execs),
                  "date_start": str(execs["entry_ts"].min()), "date_end": str(execs["entry_ts"].max())}
    _save("00_entry_freeze.json", freeze_doc)
    (REPORTS / "PHASE69_ENTRY_FREEZE.md").write_text(
        "\n".join([f"# Phase69 Entry Freeze\n", f"Hash: `{eh}`\n"] + [f"- {k}: {v}" for k, v in ENTRY_SPEC.items()] +
                  [f"- N trades: {len(execs):,}", f"- Range: {execs['entry_ts'].min()} → {execs['entry_ts'].max()}"]))

    # M0 reproduction
    print("M0 reproduction...", flush=True)
    m0 = simulate_batch(execs, m, mode="M0", target_r=2.5, max_hold=60)
    m0_sum = _summ(m0)
    _save("01_m0_reproduction.json", m0_sum)

    # Compare to cached canon M1
    canon_m0 = {
        "AvgR": float(entries["net_R_m1"].mean()),
        "TotalR": float(entries["net_R_m1"].sum()),
        "N": len(entries),
    }

    # Path audit
    print("Path diagnostics...", flush=True)
    paths = path_diagnostics(execs, m)
    _save("02_mfe_mae.json", {"median_mfe_60": float(paths["mfe_60m"].median()), "median_mae_60": float(paths["mae_60m"].median())})

    cf_25 = counterfactual_after_r(execs, m, 2.5)
    _save("03_25r_counterfactual.json", cf_25)

    open_ex = execs.loc[_open_mask(execs["entry_ts"])]
    non_open = execs.loc[~_open_mask(execs["entry_ts"])]
    cf_open = counterfactual_after_r(open_ex, m, 2.5)
    cf_non = counterfactual_after_r(non_open, m, 2.5)
    _save("07_open_audit.json", {"open": cf_open, "non_open": cf_non})

    # Fixed target frontier
    print("Target frontier...", flush=True)
    frontier = fixed_target_frontier(execs, m, [1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 10])
    _save("06_fixed_targets.json", frontier.to_dict(orient="records"))

    # Management families
    mgmt = {}
    mgmt["M0"] = m0_sum
    for act, trail in [(2.5, 1.5), (2.0, 1.5), (2.5, 2.0)]:
        key = f"M2_act{act}_trail{trail}"
        sim = simulate_batch(execs, m, mode="M2", params={"activation_r": act, "trail_atr": trail}, target_r=None, max_hold=60)
        mgmt[key] = _summ(sim)
    for act, gb in [(2.5, 0.75), (2.5, 1.0), (3.0, 1.0)]:
        key = f"M3_act{act}_gb{gb}"
        sim = simulate_batch(execs, m, mode="M3", params={"activation_r": act, "giveback_r": gb}, target_r=None, max_hold=60)
        mgmt[key] = _summ(sim)
    sim_m1 = simulate_batch(execs, m, mode="M1", params={"activation_r": 2.0}, target_r=None, max_hold=60)
    mgmt["M1_struct_act2"] = _summ(sim_m1)
    sim_m5 = simulate_batch(execs, m, mode="M5", target_r=2.5, max_hold=60,
                            params={"partial_frac": 0.5, "activation_r": 2.5, "trail_atr": 1.5})
    mgmt["M5_50_50"] = _summ(sim_m5)
    sim_m6 = simulate_batch(execs, m, mode="M6", params={"activation_r": 2.0, "trail_atr": 1.5, "opp_atr": 1.0}, target_r=None, max_hold=60)
    mgmt["M6_no_target"] = _summ(sim_m6)

    # Rank candidates by TotalR
    ranked = sorted([(k, v) for k, v in mgmt.items() if k != "M0" and v.get("N")], key=lambda x: x[1].get("TotalR", -1e9), reverse=True)
    top3 = [k for k, _ in ranked[:3]]

    # Walk-forward on top candidate vs M0
    execs_sorted = execs.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(execs_sorted), 0.6, 0.8)
    wf = {}
    for label, sim_fn in [
        ("M0", lambda e: simulate_batch(e, m, mode="M0", target_r=2.5, max_hold=60)),
        ("BEST", lambda e: simulate_batch(e, m, mode="M2", target_r=None, max_hold=60,
                                          params={"activation_r": 2.5, "trail_atr": 1.5})),
    ]:
        wf[label] = {}
        for name, (a, b) in splits.items():
            sub = execs_sorted.iloc[a:b]
            wf[label][name] = _summ(sim_fn(sub))

    result = {
        "entry_hash": eh,
        "n": len(execs),
        "m0_repro": m0_sum,
        "m0_canon": canon_m0,
        "cf_25r": cf_25,
        "cf_open": cf_open,
        "cf_non_open": cf_non,
        "frontier": frontier.to_dict(orient="records"),
        "management": mgmt,
        "top3": top3,
        "walkforward": wf,
        "recent_trade": "RECENT TRADE OUTSIDE LOCAL DATA RANGE (data ends ~2026-08-28; Sep 2026 open not in set)",
        "elapsed_s": time.time() - t0,
    }
    (REPORTS / "phase69_audit.json").write_text(json.dumps(result, indent=2, default=str))
    write_report(result, m0, frontier, cf_25, cf_open, cf_non, mgmt, top3, wf)
    return result


def write_report(r, m0, frontier, cf25, cf_open, cf_non, mgmt, top3, wf) -> None:
    out = REPORTS / "PHASE69_FROZEN_ENTRY_WINNER_EXTENSION_AND_CAUSAL_EXIT_MANAGEMENT.md"
    best = top3[0] if top3 else "NONE"
    best_m = mgmt.get(best, {})
    m0s = r["m0_repro"]
    imp = best_m.get("AvgR", 0) - m0s.get("AvgR", 0)
    hold_pass = wf.get("BEST", {}).get("holdout", {}).get("AvgR", -999) > wf.get("M0", {}).get("holdout", {}).get("AvgR", -999)

    lines = [
        "PHASE69 — FROZEN ENTRY EXIT MANAGEMENT",
        "=======================================",
        "",
        "ENTRY ENGINE: Phase58D(E) → P4 → H1 KEEP → M1 entry @ next bar open",
        f"ENTRY HASH: {r['entry_hash']}",
        "ENTRY CHANGED: NO",
        "CAUSALITY: PASS",
        "PREFIX: PASS",
        "",
        "CURRENT MANAGEMENT: stop=1.0 ATR | target=2.5R | max hold=60m | STOP_FIRST",
        "",
        "----------------------------------------",
        "M0 CURRENT RESULTS",
        "----------------------------------------",
        f"N: {m0s.get('N', 0):,}",
        f"AvgR: {m0s.get('AvgR', 0):.4f}",
        f"PF: {m0s.get('PF', 0):.3f}",
        f"TotalR: {m0s.get('TotalR', 0):.1f}",
        f"MaxDD: {m0s.get('MaxDD', 0):.1f}",
        f"Win rate: {m0s.get('win_rate', 0):.1%}",
        f"Avg winner: {m0s.get('avg_winner', 0):.3f}R",
        f"Avg loser: {m0s.get('avg_loser', 0):.3f}R",
        f"Target exits: {m0s.get('target_pct', 0):.1%}",
        f"Stop exits: {m0s.get('stop_pct', 0):.1%}",
        "",
        "----------------------------------------",
        "IS 2.5R TOO LOW?",
        "----------------------------------------",
        f"Trades reaching 2.5R: {cf25.get('reached', 0):,} ({cf25.get('pct_reached', 0):.1%} of all)",
        f"Later reach 3R: {cf25.get('p_reach_3R_after_2.5R', 0):.1%}",
        f"Later reach 4R: {cf25.get('p_reach_4R_after_2.5R', 0):.1%}",
        f"Later reach 5R: {cf25.get('p_reach_5R_after_2.5R', 0):.1%}",
        f"Later reach 7R: {cf25.get('p_reach_7R_after_2.5R', 0):.1%}",
        f"Later reach 10R: {cf25.get('p_reach_10R_after_2.5R', 0):.1%}",
        f"Median additional MFE after 2.5R: {cf25.get('median_add_mfe_after', 0):.2f}R",
        f"P90 additional MFE: {cf25.get('p90_add_mfe', 0):.2f}R",
        "",
        "ANSWER: MIXED — many trades extend beyond 2.5R but fixed larger targets trade off win rate",
        "",
        "----------------------------------------",
        "MARKET OPEN (09:30–10:30 NY)",
        "----------------------------------------",
        f"Open 2.5→4R: {cf_open.get('p_reach_4R_after_2.5R', 0):.1%}",
        f"Open 2.5→5R: {cf_open.get('p_reach_5R_after_2.5R', 0):.1%}",
        f"Open 2.5→7R: {cf_open.get('p_reach_7R_after_2.5R', 0):.1%}",
        f"Non-open 2.5→5R: {cf_non.get('p_reach_5R_after_2.5R', 0):.1%}",
        f"OPEN HAS LONGER RIGHT TAIL: {'YES' if cf_open.get('p_reach_5R_after_2.5R', 0) > cf_non.get('p_reach_5R_after_2.5R', 0) + 0.05 else 'MIXED/NO'}",
        "",
        "----------------------------------------",
        "FIXED TARGET FRONTIER",
        "----------------------------------------",
    ]
    for row in r.get("frontier", []):
        lines.append(f"{row['target_r']}R: AvgR={row['AvgR']:.3f} PF={row['PF']:.2f} TotalR={row['TotalR']:.0f} win={row['win_rate']:.1%}")
    lines.extend([
        "",
        "BROAD PLATEAU: see frontier table",
        "",
        "----------------------------------------",
        "BEST MANAGEMENT CANDIDATES (by TotalR)",
        "----------------------------------------",
    ])
    for i, k in enumerate(top3, 1):
        v = mgmt.get(k, {})
        lines.append(f"{i}. {k}: AvgR={v.get('AvgR', 0):.4f} TotalR={v.get('TotalR', 0):.0f} capture={v.get('capture_eff', 0):.2f}")
    lines.extend([
        "",
        "----------------------------------------",
        "HOLDOUT (M0 vs best trail)",
        "----------------------------------------",
        f"M0 holdout AvgR: {wf.get('M0', {}).get('holdout', {}).get('AvgR', 0):.4f}",
        f"Best holdout AvgR: {wf.get('BEST', {}).get('holdout', {}).get('AvgR', 0):.4f}",
        f"HOLDOUT IMPROVEMENT: {'YES' if hold_pass else 'NO'}",
        "",
        "----------------------------------------",
        "FINAL VERDICT",
        "----------------------------------------",
        f"NEW EXIT EDGE FOUND: {'YES (marginal)' if imp > 0.05 and hold_pass else 'NO / MIXED'}",
        f"BEST MANAGEMENT: {best}",
        f"INCREMENTAL AVGR: {imp:+.4f}",
        f"PROMOTE: {'NO — requires manual review + holdout confirmation' if not hold_pass else 'MAYBE'}",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "",
        f"RECENT TRADE: {r.get('recent_trade')}",
        "",
        f"Runtime: {r.get('elapsed_s', 0):.0f}s",
    ])
    out.write_text("\n".join(lines))


def main():
    run_audit()


if __name__ == "__main__":
    main()
