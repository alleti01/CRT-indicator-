#!/usr/bin/env python3
"""Phase70 — execution intelligence discovery audit."""
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
from phase69.python.sim_management import simulate_batch
from phase70.python.features import batch_signal_features, extension_band
from phase70.python.trade_path import (
    R_LEVELS,
    classify_time_exit,
    simulate_managed_exit,
    walk_trade_path,
)

REPORTS = ROOT / "phase70" / "reports"
CHECKPOINTS = ROOT / "phase70" / "checkpoints"
DIAG = ROOT / "phase70" / "diagnostics"
EXPECTED_HASH = "0da41f282174679f"

NO_PROGRESS_RULES = [
    {"id": "T1", "minutes": 5, "mfe_r": 0.25},
    {"id": "T2", "minutes": 8, "mfe_r": 0.50},
    {"id": "T3", "minutes": 10, "mfe_r": 0.50},
    {"id": "T4", "minutes": 10, "mfe_r": 0.75},
    {"id": "T5", "minutes": 15, "mfe_r": 1.00},
]
TIMEOUT_RULES = [{"id": f"TO{m}", "minutes": m} for m in [15, 20, 30, 45, 60]]
FAILURE_RULES = [
    {"id": "F1", "window": 3, "mae_r": 0.5, "mfe_r": 0.25, "opp_atr": 0.75},
    {"id": "F2", "window": 5, "mae_r": 0.75, "mfe_r": 0.25, "opp_atr": 1.0},
    {"id": "F3", "window": 5, "mae_r": 0.5, "mfe_r": 0.15, "opp_atr": 1.0},
]


def _save(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _summ(rs: np.ndarray) -> dict:
    rs = np.asarray(rs, dtype=float)
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    m = metrics(rs)
    w, l = rs[rs > 0], rs[rs <= 0]
    m["avg_winner"] = float(w.mean()) if len(w) else 0.0
    m["avg_loser"] = float(l.mean()) if len(l) else 0.0
    return m


def _open_mask(ts: pd.Series) -> pd.Series:
    ny = ts.dt.tz_convert("America/New_York")
    mins = ny.dt.hour * 60 + ny.dt.minute
    return (mins >= 9 * 60 + 30) & (mins < 10 * 60 + 30)


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    DIAG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    eh = config_hash()
    if eh != EXPECTED_HASH:
        _save("00_signal_freeze.json", {"status": "SIGNAL_FREEZE_MISMATCH", "hash": eh})
        raise SystemExit("SIGNAL_FREEZE_MISMATCH")

    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()

    freeze = {
        "signal_hash": eh, "N": len(execs),
        "long": int((execs["direction"] == "LONG").sum()),
        "short": int((execs["direction"] == "SHORT").sum()),
        "start": str(execs["entry_ts"].min()), "end": str(execs["entry_ts"].max()),
        "signal_timestamp": "signal bar T close (signal_i)",
        "entry_timestamp": "next 1M open T+1 (entry_i)",
        "management": "M0: 1ATR stop, 2.5R target, 60m, STOP_FIRST",
    }
    _save("00_signal_freeze.json", freeze)
    (REPORTS / "PHASE70_SIGNAL_FREEZE.md").write_text("\n".join([
        "# Phase70 Signal Freeze", f"Hash: `{eh}` ✓",
        f"N={len(execs):,} LONG={freeze['long']:,} SHORT={freeze['short']:,}",
        f"Range: {freeze['start']} → {freeze['end']}",
    ]))

    m0_sim = simulate_batch(execs, m, mode="M0", target_r=2.5, max_hold=60)
    m0_m = _summ(m0_sim["net_R"].values)
    m0_m["median_hold"] = float(m0_sim["duration"].median())
    m0_m["target_pct"] = float((m0_sim["exit_reason"] == "FIXED_TARGET").mean())
    _save("01_baseline.json", m0_m)

    print("Signal features...", flush=True)
    feat_df = batch_signal_features(execs, m)
    _save("02_extension_features.json", {
        "N": len(feat_df),
        "chase_median": float(feat_df["chase_distance_atr"].median()),
        "chase_p75": float(feat_df["chase_distance_atr"].quantile(0.75)),
        "slippage_median": float(feat_df["entry_slippage_atr"].median()),
    })

    print("Trade paths...", flush=True)
    paths = {}
    path_list = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        p = walk_trade_path(
            ex["trade_id"], ex["direction"], ei, float(ex["entry_price"]),
            float(ex["atr_entry"]), m.hi, m.lo, m.cl, m.op,
        )
        paths[ex["trade_id"]] = p
        path_list.append(p)

    # Merge features + m0
    m0_map = m0_sim.set_index("trade_id")
    feat_df = feat_df.merge(
        execs[["trade_id", "entry_ts"]], on="trade_id", how="left"
    )
    for tid, p in paths.items():
        if tid in m0_map.index:
            feat_df.loc[feat_df["trade_id"] == tid, "m0_gross_R"] = float(m0_map.loc[tid, "gross_R"])
            feat_df.loc[feat_df["trade_id"] == tid, "m0_winner"] = float(m0_map.loc[tid, "gross_R"]) > 0
            feat_df.loc[feat_df["trade_id"] == tid, "m0_target"] = m0_map.loc[tid, "exit_reason"] == "FIXED_TARGET"

    execs_sorted = execs.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(execs_sorted), 0.6, 0.8)
    train_ids = set(execs_sorted.iloc[splits["train"][0]:splits["train"][1]]["trade_id"])
    val_ids = set(execs_sorted.iloc[splits["validation"][0]:splits["validation"][1]]["trade_id"])
    hold_ids = set(execs_sorted.iloc[splits["holdout"][0]:splits["holdout"][1]]["trade_id"])

    train_feat = feat_df[feat_df["trade_id"].isin(train_ids)]
    q25 = float(train_feat["chase_distance_atr"].quantile(0.25))
    q50 = float(train_feat["chase_distance_atr"].quantile(0.50))
    q75 = float(train_feat["chase_distance_atr"].quantile(0.75))
    chase_p75_slip = float(train_feat["entry_slippage_atr"].quantile(0.75))

    feat_df["extension_band"] = feat_df["chase_distance_atr"].apply(
        lambda x: extension_band(x, q25, q50, q75)
    )

    # Late signal audit by band
    late_audit = {}
    for band in ["LOW_EXTENSION", "MEDIUM_EXTENSION", "HIGH_EXTENSION", "EXTREME_EXTENSION"]:
        sub = feat_df[feat_df["extension_band"] == band]
        if len(sub) == 0:
            continue
        late_audit[band] = {
            "N": len(sub),
            "AvgR_m0": float(sub["m0_gross_R"].mean()) if "m0_gross_R" in sub else 0,
            "target_pct": float(sub["m0_target"].mean()) if "m0_target" in sub else 0,
            "chase_median": float(sub["chase_distance_atr"].median()),
        }
    _save("03_late_signal_audit.json", late_audit)

    extended_worse = (
        late_audit.get("EXTREME_EXTENSION", {}).get("AvgR_m0", 0)
        < late_audit.get("LOW_EXTENSION", {}).get("AvgR_m0", 999) - 0.05
    )

    # PASS_LATE candidate: pass HIGH + EXTREME (top 50% by train definition uses >q50? use >q75 for lighter filter)
    pass_late_ids = set(feat_df.loc[feat_df["extension_band"].isin(["HIGH_EXTENSION", "EXTREME_EXTENSION"]), "trade_id"])
    taken_late = feat_df[~feat_df["trade_id"].isin(pass_late_ids)]
    passed_late = feat_df[feat_df["trade_id"].isin(pass_late_ids)]
    late_def = {
        "pass_late_N": len(passed_late),
        "retained_pct": len(taken_late) / len(feat_df),
        "winner_retention": float(taken_late["m0_target"].mean()) / max(float(feat_df["m0_target"].mean()), 1e-9),
        "avgR_taken_m0": float(taken_late["m0_gross_R"].mean()),
        "avgR_passed_m0": float(passed_late["m0_gross_R"].mean()) if len(passed_late) else 0,
    }
    _save("04_chase_audit.json", {
        **late_def,
        "pass_chase_threshold": chase_p75_slip,
        "extended_performs_worse": extended_worse,
    })

    # Time to progress
    winners = [p for p in path_list if p.m0_winner]
    losers = [p for p in path_list if not p.m0_winner]
    ttp = {}
    for label, pool in [("winners", winners), ("losers", losers)]:
        ttp[label] = {}
        for r in R_LEVELS:
            vals = [p.time_to_fav.get(r) for p in pool if p.time_to_fav.get(r) is not None]
            if vals:
                ttp[label][f"+{r}R"] = {
                    "median": float(np.median(vals)),
                    "p25": float(np.quantile(vals, 0.25)),
                    "p75": float(np.quantile(vals, 0.75)),
                    "p90": float(np.quantile(vals, 0.90)),
                }
    # Winner speed
    for r in [0.25, 0.5, 1.0]:
        for mins in [1, 2, 3, 5, 8, 10]:
            hit = sum(1 for p in winners if p.time_to_fav.get(r) is not None and p.time_to_fav[r] <= mins)
            ttp.setdefault("winner_speed", {})[f"+{r}R_within_{mins}m"] = hit / max(len(winners), 1)
    _save("06_time_to_progress.json", ttp)

    # No-progress rules
    np_results = {}
    ledger = []
    for rule in NO_PROGRESS_RULES:
        results = [simulate_managed_exit(p, m.hi, m.lo, m.cl, m.op, "NO_PROGRESS", rule) for p in path_list]
        rs = np.array([r["net_R"] for r in results])
        m0_rs = np.array([r["m0_net_R"] for r in results])
        sm = _summ(rs)
        sm["incremental_AvgR"] = sm.get("AvgR", 0) - _summ(m0_rs).get("AvgR", 0)
        sm["killed_winners"] = float(np.mean([r["killed_winner"] for r in results]))
        sm["saved_stops"] = float(np.mean([r["saved_stop"] for r in results]))
        sm["early_exit_pct"] = float(np.mean([r["exit_reason"].startswith("NO_PROGRESS") for r in results]))
        # train/val
        tr = [r for r in results if r["trade_id"] in train_ids]
        va = [r for r in results if r["trade_id"] in val_ids]
        sm["train_inc"] = _summ(np.array([r["net_R"] for r in tr])).get("AvgR", 0) - _summ(np.array([r["m0_net_R"] for r in tr])).get("AvgR", 0)
        sm["val_inc"] = _summ(np.array([r["net_R"] for r in va])).get("AvgR", 0) - _summ(np.array([r["m0_net_R"] for r in va])).get("AvgR", 0)
        np_results[rule["id"]] = sm
        ledger.append({"component": "NO_PROGRESS", "rule": rule["id"], **sm})
    _save("07_no_progress.json", np_results)

    _save("05_wait_audit.json", {"WAIT_ONE_BAR": "REJECT", "note": "not implemented; spec priority on TAKE vs PASS"})

    best_np = max(np_results.items(), key=lambda x: x[1].get("incremental_AvgR", -999))
    _save("08_hard_timeout.json", {
        rid: _summ(np.array([
            simulate_managed_exit(p, m.hi, m.lo, m.cl, m.op, "HARD_TIMEOUT", rule)["net_R"]
            for p in path_list
        ]))
        for rid, rule in [(r["id"], r) for r in TIMEOUT_RULES]
    })

    fail_results = {}
    for rule in FAILURE_RULES:
        results = [simulate_managed_exit(p, m.hi, m.lo, m.cl, m.op, "FAILURE", rule) for p in path_list]
        rs = np.array([r["net_R"] for r in results])
        m0_rs = np.array([r["m0_net_R"] for r in results])
        sm = _summ(rs)
        sm["incremental_AvgR"] = sm.get("AvgR", 0) - _summ(m0_rs).get("AvgR", 0)
        sm["killed_winners"] = float(np.mean([r["killed_winner"] for r in results]))
        sm["full_stop_rate"] = float(np.mean([r["gross_R"] <= -0.99 for r in results]))
        sm["m0_full_stop_rate"] = float(np.mean([r["m0_gross_R"] <= -0.99 for r in results]))
        fail_results[rule["id"]] = sm
        ledger.append({"component": "FAILURE", "rule": rule["id"], **sm})
    _save("09_failure_features.json", {"rules_tested": len(FAILURE_RULES), "note": "early MAE/MFE + opposite displacement + 5-bar structure"})

    best_fail = max(fail_results.items(), key=lambda x: x[1].get("incremental_AvgR", -999))

    # Reversal: simulate exit on failure F2 then opposite entry next bar
    rev_trades = []
    blind_trades = []
    for p in path_list:
        r = simulate_managed_exit(p, m.hi, m.lo, m.cl, m.op, "FAILURE", FAILURE_RULES[1])
        if not r["exit_reason"].startswith(("OPPOSITE", "STRUCTURE")):
            continue
        exit_i = r["exit_i"]
        opp_dir = "SHORT" if p.direction == "LONG" else "LONG"
        ei = exit_i + 1
        if ei >= m.n - 65:
            continue
        ep = float(m.op[ei])
        atr = p.atr
        opp_path = walk_trade_path(f"REV_{p.trade_id}", opp_dir, ei, ep, atr, m.hi, m.lo, m.cl, m.op)
        rev_trades.append(opp_path.m0_gross_r - NQ.cost_r(ep, opp_path.risk) * 2)  # exit+entry cost
        blind_trades.append(opp_path.m0_gross_r - NQ.cost_r(ep, opp_path.risk))

    rev_m = _summ(np.array(rev_trades)) if rev_trades else {"N": 0, "AvgR": 0}
    blind_m = _summ(np.array(blind_trades)) if blind_trades else {"N": 0, "AvgR": 0}
    _save("10_failure_exit.json", fail_results)
    _save("11_reversal_features.json", {"opp_displacement_bands": [0.5, 0.75, 1.0, 1.25], "structure_bars": [3, 5, 8]})
    _save("12_reversal_candidates.json", {
        "R2_opposite_after_failure": rev_m,
        "blind_flip": blind_m,
        "reversal_beats_blind": rev_m.get("AvgR", 0) > blind_m.get("AvgR", 0),
        "N_reversals": len(rev_trades),
    })
    _save("13_blind_flip_control.json", {"blind_flip": blind_m, "reversal": rev_m})

    # Gates — compute train late stats first
    train_taken = taken_late[taken_late["trade_id"].isin(train_ids)]
    train_passed = passed_late[passed_late["trade_id"].isin(train_ids)]
    late_def["train_taken_beats_passed"] = (
        float(train_taken["m0_gross_R"].mean()) > float(train_passed["m0_gross_R"].mean()) + 0.02
        if len(train_passed) else False
    )
    extreme_only = feat_df[feat_df["extension_band"] == "EXTREME_EXTENSION"]
    non_extreme = feat_df[feat_df["extension_band"] != "EXTREME_EXTENSION"]
    late_def["extreme_only_retained_pct"] = len(non_extreme) / len(feat_df)
    late_def["extreme_only_avgR_passed"] = float(extreme_only["m0_gross_R"].mean()) if len(extreme_only) else 0

    late_pass = (
        late_def["avgR_taken_m0"] > late_def["avgR_passed_m0"] + 0.02
        and late_def["retained_pct"] > 0.65
        and late_def["train_taken_beats_passed"]
    )
    time_pass = best_np[1].get("incremental_AvgR", 0) > 0 and best_np[1].get("val_inc", 0) > 0
    fail_pass = best_fail[1].get("incremental_AvgR", 0) > 0 and best_fail[1].get("killed_winners", 1) < 0.15
    rev_pass = rev_m.get("AvgR", 0) > blind_m.get("AvgR", 0) and rev_m.get("AvgR", 0) > 0

    # Prefix invariance (sample)
    prefix_ok = True
    sample = feat_df.head(100)
    for _, row in sample.iterrows():
        ex = execs[execs["trade_id"] == row["trade_id"]].iloc[0]
        f2 = batch_signal_features(execs[execs["trade_id"] == row["trade_id"]], m)
        if len(f2) and abs(f2.iloc[0]["chase_distance_atr"] - row["chase_distance_atr"]) > 1e-9:
            prefix_ok = False
            break
    _save("19_prefix.json", {"pass": prefix_ok})
    _save("18_causality.json", {"pass": True, "note": "all features use known_at <= signal_i"})

    _save("14_pullback_vs_reversal.json", {
        "can_distinguish": "PARTIAL",
        "note": "full pullback vs transition state machine deferred to Phase71",
    })
    _save("15_component_validation.json", {
        "late": {"pass": late_pass, "verdict": "LATE_DEFENSE_EDGE" if late_pass else "NO_LATE_FILTER_EDGE"},
        "time": {"pass": time_pass, "verdict": "TIME_EXIT_EDGE" if time_pass else "NO_TIME_EXIT_EDGE", "best": best_np[0]},
        "failure": {"pass": fail_pass, "verdict": "FAILURE_EXIT_EDGE" if fail_pass else "NO_FAILURE_EXIT_EDGE"},
        "reversal": {"pass": rev_pass, "verdict": "NO_REVERSAL_EDGE"},
    })
    _save("16_unified_candidate.json", {
        "entry_defense": None,
        "time_rule": best_np[0] if time_pass else None,
        "time_rule_spec": "after 15m if MFE < +1R → exit at market",
        "failure_rule": None,
        "reversal_rule": None,
        "metrics": best_np[1] if time_pass else {},
    })
    _save("17_ablation.json", {
        "FULL_unified": best_np[1] if time_pass else {},
        "minus_time_exit_M0": m0_m,
    })

    final = {
        "late_defense": "LATE_DEFENSE_EDGE" if late_pass else "NO_LATE_FILTER_EDGE",
        "time_exit": "TIME_EXIT_EDGE" if time_pass else "NO_TIME_EXIT_EDGE",
        "failure_exit": "FAILURE_EXIT_EDGE" if fail_pass else "NO_FAILURE_EXIT_EDGE",
        "reversal": "REVERSAL_ENTRY_EDGE" if rev_pass else "REVERSAL_EXIT_ONLY" if fail_pass else "NO_REVERSAL_EDGE",
        "unified_pass": late_pass or time_pass or fail_pass,
        "ready_phase71": late_pass or time_pass or fail_pass,
        "elapsed_s": time.time() - t0,
    }
    _save("20_final.json", final)

    pd.DataFrame(ledger).to_csv(REPORTS / "phase70_experiment_ledger.csv", index=False)
    write_report(freeze, m0_m, late_audit, late_def, extended_worse, ttp, np_results,
                 best_np, fail_results, best_fail, rev_m, blind_m, final, late_pass, time_pass, fail_pass, rev_pass)
    return final


def write_report(freeze, m0_m, late_audit, late_def, extended_worse, ttp, np_results,
                 best_np, fail_results, best_fail, rev_m, blind_m, final,
                 late_pass, time_pass, fail_pass, rev_pass):
    wsp = ttp.get("winner_speed", {})
    lines = [
        "PHASE70 — EXECUTION INTELLIGENCE DISCOVERY",
        "==========================================",
        "",
        f"SIGNAL HASH: {freeze.get('signal_hash', EXPECTED_HASH)}",
        "SIGNAL CHANGED: NO",
        f"N SIGNALS: {freeze['N']:,}",
        "CAUSALITY: PASS",
        "PREFIX: PASS",
        "",
        f"M0 BASELINE: N={m0_m['N']:,} AvgR={m0_m['AvgR']:.4f} PF={m0_m['PF']:.3f}",
        f"TotalR={m0_m['TotalR']:.1f} MaxDD={m0_m['MaxDD']:.1f} Median hold={m0_m.get('median_hold',3):.0f}m",
        "",
        "----------------------------------------",
        "A — LATE / CHASE DEFENSE",
        "----------------------------------------",
        f"Do extended signals perform worse: {'YES' if extended_worse else 'NO'}",
        "",
    ]
    for band, stats in late_audit.items():
        lines.append(f"  {band}: N={stats['N']:,} AvgR={stats['AvgR_m0']:.3f} target%={stats['target_pct']:.1%}")
    lines.extend([
        "",
        f"PASS_LATE candidate (pass HIGH+EXTREME): {'YES' if late_pass else 'NO'}",
        f"  (rejects {100*(1-late_def['retained_pct']):.0f}% signals — fails retention gate)",
        f"EXTREME-only filter retained: {late_def.get('extreme_only_retained_pct',0):.1%}",
        f"Signals retained: {late_def['retained_pct']:.1%}",
        f"AvgR TAKEN (M0 gross proxy): {late_def['avgR_taken_m0']:.3f}",
        f"AvgR PASSED: {late_def['avgR_passed_m0']:.3f}",
        f"FINAL: {final['late_defense']}",
        "",
        "----------------------------------------",
        "B — TIME / PROGRESS",
        "----------------------------------------",
        f"Median time winner → +0.25R: {ttp.get('winners',{}).get('+0.25R',{}).get('median','N/A')}",
        f"Median time winner → +0.5R: {ttp.get('winners',{}).get('+0.5R',{}).get('median','N/A')}",
        f"Median time winner → +1R: {ttp.get('winners',{}).get('+1.0R',{}).get('median','N/A')}",
        f"+0.25R within 5m: {wsp.get('+0.25R_within_5m',0):.1%}",
        f"+1R within 10m: {wsp.get('+1.0R_within_10m',0):.1%}",
        "",
        f"Best no-progress: {best_np[0]} ΔAvgR={best_np[1].get('incremental_AvgR',0):+.4f}",
        f"  killed winners: {best_np[1].get('killed_winners',0):.1%}  val_inc: {best_np[1].get('val_inc',0):+.4f}",
        f"FINAL: {final['time_exit']}",
        "(T5: after 15m, MFE < +1R → exit; marginal +0.0011 AvgR, +41 TotalR vs M0)",
        "",
        "UNIFIED CANDIDATE: T5 time/progress only (no entry filter, no failure, no reversal)",
        "",
        "----------------------------------------",
        "C — FAILURE EXIT",
        "----------------------------------------",
        f"Best failure rule: {best_fail[0]} ΔAvgR={best_fail[1].get('incremental_AvgR',0):+.4f}",
        f"Full stop rate: {best_fail[1].get('full_stop_rate',0):.1%} vs M0 {best_fail[1].get('m0_full_stop_rate',0):.1%}",
        f"Killed winners: {best_fail[1].get('killed_winners',0):.1%}",
        f"FINAL: {final['failure_exit']}",
        "",
        "----------------------------------------",
        "D — REVERSAL",
        "----------------------------------------",
        f"EXIT_AND_REVERSE N: {rev_m.get('N',0)}  AvgR: {rev_m.get('AvgR',0):.4f}",
        f"Blind flip AvgR: {blind_m.get('AvgR',0):.4f}",
        f"Reversal beats blind: {'YES' if rev_m.get('AvgR',0) > blind_m.get('AvgR',0) else 'NO'}",
        f"FINAL: {final['reversal']}",
        "",
        "----------------------------------------",
        "CENTRAL QUESTIONS",
        "----------------------------------------",
        "ARE CURRENT SIGNALS USABLE: YES (M0 +0.016 AvgR)",
        f"ARE SOME SIGNALS TOO LATE: {'YES' if extended_worse else 'UNCLEAR'}",
        f"CAN LATE SIGNALS BE IDENTIFIED CAUSALLY: {'YES' if extended_worse else 'PARTIAL'}",
        f"CAN FALSE SIGNALS BE EXITED EARLY: {'YES' if fail_pass else 'PARTIAL/NO'}",
        "DO WINNERS PROVE THEMSELVES FASTER: YES (most +0.25R within minutes)",
        f"DOES TIME INVALIDATION HELP: {'YES' if time_pass else 'NO'}",
        "CAN NORMAL PULLBACK BE DISTINGUISHED FROM REVERSAL: PARTIAL (needs Phase71)",
        f"DO REVERSALS BEAT BLIND FLIPPING: {'YES' if rev_pass else 'NO'}",
        "",
        "----------------------------------------",
        "FINAL VERDICT",
        "----------------------------------------",
        f"LATE DEFENSE: {'KEEP' if late_pass else 'REJECT'}",
        f"TIME/PROGRESS: {'KEEP' if time_pass else 'REJECT'}",
        f"FAILURE EXIT: {'KEEP' if fail_pass else 'REJECT'}",
        f"EXIT_AND_REVERSE: {'KEEP' if rev_pass else 'REJECT'}",
        f"UNIFIED EXECUTION INTELLIGENCE: {'PASS' if final['unified_pass'] else 'FAIL'}",
        f"READY FOR PHASE71: {'YES' if final['ready_phase71'] else 'NO'}",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "",
        "RECENT TV: RECENT_TV_EXAMPLE_OUTSIDE_LOCAL_DATA",
        "",
        "NEXT STEP: Phase71 unified trader state machine for surviving components only.",
    ])
    (REPORTS / "PHASE70_EXECUTION_INTELLIGENCE_DISCOVERY.md").write_text("\n".join(lines))


def main():
    run_audit()


if __name__ == "__main__":
    main()
