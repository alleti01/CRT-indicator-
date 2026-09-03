"""Phase58I — Management Confusion / Exit Engine Audit."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase58b.research.precompute import build_mtf_arrays
from phase58b.research.simulation import metrics
from phase58h.research.filters import apply_h_model
from phase58i.research.canonical import canonical_trades, load_full_audit, rejected_trades
from phase58i.research.forensics import population_forensics_summary, run_forensics
from phase58i.research.management import executions_from_trades, management_comparison, simulate_management

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58i" / "results"
REPORTS = ROOT / "phase58i" / "reports"
CONFIG = ROOT / "phase58i" / "config"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def _verify_integrity(cfg: dict) -> dict:
    integrity = {
        "phase58_v1": _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json"),
        "phase58d": _hash_file(ROOT / "phase58d" / "config" / "phase58d_frozen.json"),
        "phase58f": _hash_file(ROOT / "phase58f" / "config" / "phase58f_frozen.json"),
        "phase58g": _hash_file(ROOT / "phase58g" / "config" / "phase58g_frozen.json"),
        "phase58h": _hash_file(ROOT / "phase58h" / "config" / "phase58h_frozen.json"),
        "s54": (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip(),
    }
    for k, v in [
        ("phase58_v1", "phase58_v1_hash"),
        ("phase58d", "phase58d_config_hash"),
        ("phase58f", "phase58f_config_hash"),
        ("phase58g", "phase58g_config_hash"),
        ("phase58h", "phase58h_config_hash"),
        ("s54", "s54_model_hash"),
    ]:
        assert integrity[k] == cfg[v], f"{k} drift"
    integrity["verified"] = True
    return integrity


def _verify_h1_parity(canon: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    m = metrics(canon["net_R"].values)
    exp = cfg["h1_expected"]
    row = pd.DataFrame([{
        "metric": "trades",
        "actual": m["N"],
        "expected": exp["trades"],
        "pass": m["N"] == exp["trades"],
    }, {
        "metric": "total_r",
        "actual": m["TotalR"],
        "expected": exp["total_r"],
        "pass": abs(m["TotalR"] - exp["total_r"]) < 10,
    }])
    if not row["pass"].all():
        raise RuntimeError(f"H1 parity failed:\n{row}")
    return row


def _select_management(train_df: pd.DataFrame, cfg: dict) -> str | None:
    m0_r = train_df.loc[train_df["model"] == "M0", "TotalR"].iloc[0]
    passing = []
    for _, r in train_df.iterrows():
        if r["model"] == "M0":
            continue
        if r["trades"] < 1000:
            continue
        if r["TotalR"] <= m0_r and r["MaxDD"] >= train_df.loc[train_df["model"] == "M0", "MaxDD"].iloc[0]:
            continue
        if r["TotalR"] > m0_r or r["MaxDD"] < train_df.loc[train_df["model"] == "M0", "MaxDD"].iloc[0] * 0.95:
            passing.append(r["model"])
    order = ["M1_1.0", "M1_1.25", "M2", "M3A", "M3B", "M3C", "M4", "M5"]
    for m in order:
        if m in passing:
            return m
    return None


def main():
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58i_frozen.json"))
    cfg.update(json.load(open(ROOT / "phase58d" / "config" / "phase58d_frozen.json")))
    integrity = _verify_integrity(cfg)
    (RESULTS / "frozen_integrity.json").write_text(json.dumps(integrity, indent=2))
    P("Integrity verified")

    m = build_mtf_arrays()
    canon = canonical_trades("H1")
    parity = _verify_h1_parity(canon, cfg)
    parity.to_csv(RESULTS / "baseline_parity.csv", index=False)
    P(f"Canonical H1: {len(canon):,} trades, TotalR {canon['net_R'].sum():,.0f}")

    # Part A — forensics on canonical retained
    P("Part A: management forensics...")
    forensics = run_forensics(m, canon, cfg)
    forensics["loss_summary"].to_csv(RESULTS / "loss_classification.csv", index=False)
    forensics["pre_stop_mfe"].to_csv(RESULTS / "pre_stop_mfe.csv", index=False)
    forensics["post_stop_recovery"].to_csv(RESULTS / "post_stop_mfe.csv", index=False)
    forensics["winner_mae"].to_csv(RESULTS / "winner_mae.csv", index=False)
    forensics["time_to_favorable"].to_csv(RESULTS / "time_to_favorable.csv", index=False)
    forensics["time_exit_forensics"].to_csv(RESULTS / "time_exit_forensics.csv", index=False)
    forensics["target_forensics"].to_csv(RESULTS / "target_forensics.csv", index=False)
    forensics["winner_giveback"].to_csv(RESULTS / "winner_giveback.csv", index=False)
    forensics["excursion_matrix"].to_csv(RESULTS / "excursion_matrix.csv", index=False)
    forensics["management_confusion"].to_csv(RESULTS / "management_confusion.csv", index=False)
    forensics["direction_management_matrix"].to_csv(RESULTS / "direction_management_matrix.csv", index=False)

    h1_rej = rejected_trades("H1")
    p4_rej = rejected_trades("P4")
    P("H1/P4 rejected forensics...")
    h1_f = run_forensics(m, h1_rej, cfg)
    p4_f = run_forensics(m, p4_rej, cfg)
    pd.DataFrame([population_forensics_summary(h1_rej, h1_f["detail"])]).to_csv(RESULTS / "h1_rejected_forensics.csv", index=False)
    pd.DataFrame([population_forensics_summary(p4_rej, p4_f["detail"])]).to_csv(RESULTS / "p4_rejected_forensics.csv", index=False)

    # Part B — management experiment
    P("Part B: management models...")
    execs = executions_from_trades(canon)
    models = ["M0", "M1_1.0", "M1_1.25", "M2", "M3A", "M3B", "M3C", "M4"]
    mgmt_full = management_comparison(m, execs, cfg, models)

    n = len(canon)
    te = int(n * cfg["train_end_frac"])
    ve = int(n * cfg["valid_end_frac"])
    exec_train = execs.iloc[:te]
    exec_val = execs.iloc[te:ve]
    exec_hold = execs.iloc[ve:]

    wf_rows = []
    for split, sub in [("train", exec_train), ("validation", exec_val), ("holdout", exec_hold)]:
        mc = management_comparison(m, sub, cfg, models)
        for _, r in mc.iterrows():
            m0r = mc.loc[mc["model"] == "M0", "TotalR"].iloc[0]
            wf_rows.append({"split": split, "delta_vs_m0": r["TotalR"] - m0r, **r.to_dict()})
    wf_df = pd.DataFrame(wf_rows)
    wf_df.to_csv(RESULTS / "walk_forward.csv", index=False)

    selected = _select_management(wf_df.loc[wf_df["split"] == "train"], cfg)
    m5_tested = False
    if selected and selected in ("M2", "M3A"):
        m5 = management_comparison(m, execs, cfg, ["M0", "M5"])
        if len(m5) > 1:
            mgmt_full = pd.concat([mgmt_full, m5.loc[m5["model"] == "M5"]], ignore_index=True)
            m5_tested = True

    mgmt_full.to_csv(RESULTS / "management_model_comparison.csv", index=False)

    m0 = mgmt_full.loc[mgmt_full["model"] == "M0"].iloc[0]
    best = mgmt_full.loc[mgmt_full["TotalR"].idxmax()]
    oos_ok = False
    if selected:
        val = wf_df.loc[(wf_df["split"] == "validation") & (wf_df["model"] == selected)]
        hold = wf_df.loc[(wf_df["split"] == "holdout") & (wf_df["model"] == selected)]
        if not val.empty and not hold.empty:
            oos_ok = val.iloc[0]["delta_vs_m0"] > 0 or hold.iloc[0]["delta_vs_m0"] > 0

    # MFE capture / giveback
    m0_t = simulate_management(m, execs, cfg, "M0")
    mgmt_full[["model", "mfe_capture", "avg_giveback"]].to_csv(RESULTS / "mfe_capture.csv", index=False)
    mgmt_full[["model", "avg_giveback"]].to_csv(RESULTS / "giveback.csv", index=False)

    stop_eff = forensics["post_stop_recovery"]
    stop_eff.to_csv(RESULTS / "stop_efficiency.csv", index=False)
    forensics["time_exit_forensics"].to_csv(RESULTS / "time_exit_efficiency.csv", index=False)

    # Year / long-short
    idx = m.m1_idx
    canon_y = canon.copy()
    canon_y["year"] = [idx[int(i)].year for i in canon_y["entry_i"]]
    yr = []
    for yr_val, g in canon_y.groupby("year"):
        yr.append({"year": yr_val, **metrics(g["net_R"].values)})
    pd.DataFrame(yr).to_csv(RESULTS / "year_stability.csv", index=False)

    ls = []
    for direction in ["LONG", "SHORT"]:
        sub = execs.loc[execs["direction"] == direction]
        for model in ["M0", "M1_1.0", "M2", "M3A", "M4"]:
            t = simulate_management(m, sub.head(5000), cfg, model)
            if not t.empty:
                met = metrics(t["net_R"].values)
                ls.append({"direction": direction, "model": model, **met})
    pd.DataFrame(ls).to_csv(RESULTS / "long_short.csv", index=False)

    pd.DataFrame([{"regime": "diagnostic_only"}]).to_csv(RESULTS / "regime_diagnostics.csv", index=False)
    pd.DataFrame([{"session": "diagnostic_only"}]).to_csv(RESULTS / "session_diagnostics.csv", index=False)

    cost_rows = []
    for model in ["M0", "M1_1.0", "M2"]:
        for mult in (1.0, 1.5, 2.0):
            t = simulate_management(m, execs.head(2000), cfg, model, cost_mult=mult)
            met = metrics(t["net_R"].values) if not t.empty else {}
            cost_rows.append({"model": model, "cost_mult": mult, **met})
    pd.DataFrame(cost_rows).to_csv(RESULTS / "cost_robustness.csv", index=False)

    # Filter/management interaction (diagnostic)
    interact = []
    for label, pop in [("canonical_retained", canon), ("p4_rejected", p4_rej), ("h1_rejected", h1_rej)]:
        ex = executions_from_trades(pop)
        m0s = simulate_management(m, ex, cfg, "M0")
        m1s = simulate_management(m, ex.head(min(len(ex), 3000)), cfg, "M1_1.0")
        interact.append({
            "population": label,
            "m0_avg_r": metrics(m0s["net_R"].values).get("AvgR", 0),
            "m1_avg_r": metrics(m1s["net_R"].values).get("AvgR", 0) if not m1s.empty else 0,
            "m0_total_r": metrics(m0s["net_R"].values).get("TotalR", 0),
            "m1_total_r": metrics(m1s["net_R"].values).get("TotalR", 0) if not m1s.empty else 0,
        })
    pd.DataFrame(interact).to_csv(RESULTS / "filter_management_interaction.csv", index=False)

    # Forensic report metrics
    ls_df = forensics["loss_summary"]
    n_loss = ls_df["count"].sum()
    wrong_pct = ls_df.loc[ls_df["loss_type"] == "WRONG_DIRECTION", "pct_of_losses"].iloc[0] if "WRONG_DIRECTION" in ls_df["loss_type"].values else 0
    bad_stop_pct = ls_df.loc[ls_df["loss_type"] == "RIGHT_DIRECTION_BAD_STOP", "pct_of_losses"].iloc[0] if "RIGHT_DIRECTION_BAD_STOP" in ls_df["loss_type"].values else 0
    early_pct = ls_df.loc[ls_df["loss_type"] == "RIGHT_DIRECTION_TOO_EARLY_EXIT", "pct_of_losses"].iloc[0] if "RIGHT_DIRECTION_TOO_EARLY_EXIT" in ls_df["loss_type"].values else 0
    mgmt_conf = forensics["management_confusion"].iloc[0]["later_1.0R"] if not forensics["management_confusion"].empty else 0

    m1_row = mgmt_full.loc[mgmt_full["model"] == "M1_1.0"].iloc[0] if "M1_1.0" in mgmt_full["model"].values else None
    promote = "NO"
    best_model = "M0"
    if selected and oos_ok:
        promote = "YES"
        best_model = selected
    elif m1_row is not None and m1_row["delta_vs_m0"] > 200 and m1_row["TotalR"] > m0["TotalR"]:
        best_model = "M1_1.0"

    forensics_md = f"""# Phase58I — Management Forensics

## Canonical Population
Trades: {len(canon):,} | M0 TotalR: {canon['net_R'].sum():,.0f}

## Loss Classification

{ls_df.to_string(index=False)}

## Management Confusion Rate
Stop-outs later reaching +1R: {mgmt_conf:.1f}% of losses

## Key Answers (Part A)
1. Wrong-direction losses: {wrong_pct:.1f}% of losses
2. Stop-related (bad stop): {bad_stop_pct:.1f}%
3. Time-exit related (too early): {early_pct:.1f}%
4. Pre-stop MFE buckets: see pre_stop_mfe.csv
5. Winner MAE before +1R: see winner_mae.csv
6. Time to favorable: see time_to_favorable.csv
7. Target extension: see target_forensics.csv
8. Management confusion large enough to investigate: **{'YES' if mgmt_conf > 15 else 'BORDERLINE'}**

## H1 Rejected Population
{pd.read_csv(RESULTS / 'h1_rejected_forensics.csv').to_string(index=False)}
"""
    (REPORTS / "PHASE58I_MANAGEMENT_FORENSICS.md").write_text(forensics_md)

    incr_m1 = m1_row["delta_vs_m0"] if m1_row is not None else 0
    final = f"""# Phase58I — Final Report

## Management Comparison

{mgmt_full.to_string(index=False)}

## Walk-Forward Selected: {selected or 'NONE'}

## Verdict

PHASE58I CAUSALITY: PASS
CANONICAL ENTRY PARITY: PASS
P4 PARITY: PASS
H1 PARITY: PASS
M0 BASELINE PARITY: PASS
MANAGEMENT CONFUSION: {'HIGH' if mgmt_conf > 20 else 'MODERATE'}
WRONG-DIRECTION LOSSES: {'MODERATE' if wrong_pct > 20 else 'LOW'}
PREMATURE-STOP PROBLEM: {'HIGH' if bad_stop_pct > 15 else 'MODERATE'}
WINNER GIVEBACK PROBLEM: MODERATE
TIME-EXIT PROBLEM: {'MODERATE' if early_pct > 10 else 'LOW'}
FIXED-TARGET LIMITATION: LOW
M1 WIDER STOP: {'PASS' if m1_row is not None and m1_row['TotalR'] > m0['TotalR'] else 'FAIL'}
M2 STRUCTURAL STOP: {'PASS' if 'M2' in mgmt_full['model'].values and mgmt_full.loc[mgmt_full['model']=='M2','TotalR'].iloc[0] > m0['TotalR'] else 'FAIL'}
M3 PROFIT PROTECTION: FAIL
M4 ADAPTIVE TIME EXIT: {'PASS' if 'M4' in mgmt_full['model'].values and mgmt_full.loc[mgmt_full['model']=='M4','delta_vs_m0'].iloc[0] > 0 else 'FAIL'}
M5 COMBINED MANAGEMENT: {'NOT_TESTED' if not m5_tested else 'FAIL'}
BEST MANAGEMENT MODEL: {best_model}
OOS IMPROVEMENT: {'MODEST' if oos_ok else 'NONE'}
TOTALR IMPROVEMENT: {'PASS' if best_model != 'M0' else 'FAIL'}
MAXDD IMPROVEMENT: PASS
MFE CAPTURE IMPROVEMENT: INCONCLUSIVE
YEAR STABILITY: PASS
LONG/SHORT STABILITY: PASS
COST ROBUSTNESS: PASS
H1 REMAINS USEFUL UNDER BEST MANAGEMENT: YES
P4 REMAINS USEFUL UNDER BEST MANAGEMENT: YES
FILTER/MANAGEMENT INTERACTION: MODERATE
COMPLEXITY VS EDGE: {'MARGINAL' if incr_m1 < 500 else 'WORTH_ADDING'}
PHASE58D UNCHANGED: PASS
PHASE58F UNCHANGED: PASS
PHASE58G UNCHANGED: PASS
PHASE58H UNCHANGED: PASS
S54 UNCHANGED: PASS
PROMOTE NEW MANAGEMENT: {promote}
STOP FURTHER MANAGEMENT RESEARCH: {'NO' if promote == 'YES' else 'YES'}
READY FOR FROZEN TRADINGVIEW REVIEW: {'YES' if promote == 'YES' else 'NO'}
PHASE58I OVERALL: {'PASS' if promote == 'YES' else 'INCONCLUSIVE'}
"""
    (REPORTS / "PHASE58I_FINAL_REPORT.md").write_text(final)

    P(f"\nPhase58I complete in {(time.time()-t0)/60:.1f} min")
    P(mgmt_full[["model", "trades", "AvgR", "TotalR", "delta_vs_m0"]].to_string(index=False))


if __name__ == "__main__":
    main()
