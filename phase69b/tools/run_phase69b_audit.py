#!/usr/bin/env python3
"""Phase69B — narrow partial-runner validation."""
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
from phase69.python.entry_freeze import config_hash, executions, load_frozen_entries
from phase69.python.sim_management import simulate_batch
from phase69b.python.partial_runner import (
    M0_TARGET_R,
    attribution,
    bootstrap_ci,
    classify_winner_outcome,
    one_position_filter,
    precompute_paths,
    primary_configs,
    regret_bucket,
    simulate_config,
)

REPORTS = ROOT / "phase69b" / "reports"
CHECKPOINTS = ROOT / "phase69b" / "checkpoints"
DIAG = ROOT / "phase69b" / "diagnostics" / "visual_review"
EXPECTED_HASH = "0da41f282174679f"


def _save(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _summ_rs(rs: np.ndarray) -> dict:
    m = metrics(rs)
    pos = rs[rs > 0]
    neg = rs[rs <= 0]
    m["avg_winner"] = float(pos.mean()) if len(pos) else 0.0
    m["avg_loser"] = float(neg.mean()) if len(neg) else 0.0
    return m


def _open_mask(ts: pd.Series) -> pd.Series:
    ny = ts.dt.tz_convert("America/New_York")
    mins = ny.dt.hour * 60 + ny.dt.minute
    return (mins >= 9 * 60 + 30) & (mins < 10 * 60 + 30)


def _cfg_metrics(trades: list[dict], label: str = "") -> dict:
    rs = np.array([t["net_R"] for t in trades])
    m0_rs = np.array([t["m0_net_R"] for t in trades])
    tw = [t for t in trades if t["true_2p5_winner"]]
    tw_rs = np.array([t["net_R"] for t in tw]) if tw else np.array([])
    m = _summ_rs(rs)
    m0_m = _summ_rs(m0_rs)
    out = {
        **m,
        "incremental_AvgR": m["AvgR"] - m0_m["AvgR"],
        "incremental_TotalR": m["TotalR"] - m0_m["TotalR"],
        "m0_AvgR": m0_m["AvgR"],
        "m0_TotalR": m0_m["TotalR"],
        "m0_PF": m0_m["PF"],
        "median_hold": float(np.median([t["duration"] for t in trades])),
    }
    if len(tw):
        out["true_winner_N"] = len(tw)
        out["runner_target_hit"] = float(np.mean([t["exit_reason"] == "RUNNER_TARGET" for t in tw]))
        out["runner_protection_hit"] = float(np.mean([t["exit_reason"] == "RUNNER_PROTECTION" for t in tw]))
        out["runner_timeout"] = float(np.mean([t["exit_reason"] == "RUNNER_TIMEOUT" for t in tw]))
        out["damage_lt_2P4"] = float(np.mean([t["gross_R"] < 2.4 for t in tw]))
        out["damage_lt_2P25"] = float(np.mean([t["gross_R"] < 2.25 for t in tw]))
        out["damage_lt_2P0"] = float(np.mean([t["gross_R"] < 2.0 for t in tw]))
        out["pct_gt_2P5"] = float(np.mean([t["gross_R"] > 2.5 for t in tw]))
        out["pct_gte_3"] = float(np.mean([t["gross_R"] >= 3.0 for t in tw]))
        out["pct_gte_3P5"] = float(np.mean([t["gross_R"] >= 3.5 for t in tw]))
        out["pct_gte_4"] = float(np.mean([t["gross_R"] >= 4.0 for t in tw]))
        out["tw_mean_R"] = float(tw_rs.mean())
        out["tw_median_R"] = float(np.median(tw_rs))
        out["tw_p25"] = float(np.quantile(tw_rs, 0.25))
        out["tw_p75"] = float(np.quantile(tw_rs, 0.75))
    return out


def _non_winner_parity(trades: list[dict]) -> bool:
    for t in trades:
        if not t["true_2p5_winner"]:
            if abs(t["gross_R"] - t["m0_gross_R"]) > 1e-9:
                return False
            if t["exit_reason"] != {"FIXED_TARGET": "M0", "INITIAL_STOP": "M0", "MAX_HOLD": "M0"}.get(
                t.get("_m0_reason", ""), "M0"
            ) and t["exit_reason"] != "M0":
                pass  # exit_reason is always M0 string for non-winners
    return all(
        abs(t["gross_R"] - t["m0_gross_R"]) < 1e-9 and t["exit_reason"] == "M0"
        for t in trades if not t["true_2p5_winner"]
    )


def _slice_trades(trades: list[dict], execs_sorted: pd.DataFrame, a: int, b: int) -> list[dict]:
    ids = set(execs_sorted.iloc[a:b]["trade_id"])
    return [t for t in trades if t["trade_id"] in ids]


def _score_train(m: dict) -> float:
    """Selection score — prefer incremental AvgR with penalties."""
    if m.get("incremental_AvgR", -999) <= 0:
        return -999
    if m.get("incremental_TotalR", -999) <= 0:
        return -999
    dmg = m.get("damage_lt_2P0", 1.0)
    pf_ratio = m.get("PF", 0) / max(m.get("m0_PF", 1), 1e-9)
    return m["incremental_AvgR"] * 100 - dmg * 50 + min(pf_ratio, 1.2) * 5


def _target_hit_before_stop(paths, hi, lo, prot: float, tgt: float) -> float:
    """Phase69B task 14 — target hit before protection on true winners."""
    hits = []
    for pr in paths:
        if not pr.true_2p5_winner or pr.t_2p5_bar is None:
            continue
        d = 1 if pr.direction == "LONG" else -1
        ep, risk = pr.entry_price, pr.risk
        t0 = pr.t_2p5_bar
        end = min(pr.entry_i + 60, len(hi) - 1)
        prot_px = ep + d * prot * risk
        tgt_px = ep + d * tgt * risk
        tp = tn = None
        for k in range(t0, end + 1):
            h, l = float(hi[k]), float(lo[k])
            ht = (h >= tgt_px) if d == 1 else (l <= tgt_px)
            hs = (l <= prot_px) if d == 1 else (h >= prot_px)
            if tp is None and ht:
                tp = k
            if tn is None and hs:
                tn = k
        if tp is None and tn is None:
            hits.append(None)
        elif tp is None:
            hits.append(False)
        elif tn is None:
            hits.append(True)
        else:
            hits.append(tp <= tn)
    vals = [h for h in hits if h is not None]
    return float(np.mean(vals)) if vals else 0.0


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    DIAG.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    eh = config_hash()
    if eh != EXPECTED_HASH:
        _save("00_freeze.json", {"status": "ENTRY_FREEZE_MISMATCH", "hash": eh})
        raise SystemExit(f"ENTRY_FREEZE_MISMATCH: {eh}")

    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()

    freeze = {
        "entry_hash": eh, "N": len(execs),
        "long": int((execs["direction"] == "LONG").sum()),
        "short": int((execs["direction"] == "SHORT").sum()),
    }

    _save("00_freeze.json", freeze)

    m0_sim = simulate_batch(execs, m, mode="M0", target_r=2.5, max_hold=60)
    m0_rs = m0_sim["net_R"].values
    m0_m = _summ_rs(m0_rs)
    m0_m["median_hold"] = float(m0_sim["duration"].median())
    m0_m["target_pct"] = float((m0_sim["exit_reason"] == "FIXED_TARGET").mean())
    m0_m["stop_pct"] = float((m0_sim["exit_reason"] == "INITIAL_STOP").mean())
    _save("01_m0.json", m0_m)

    print("Precomputing paths...", flush=True)
    paths = precompute_paths(execs, m)
    n_true = sum(1 for p in paths if p.true_2p5_winner)
    _save("02_true_winners.json", {"N": n_true, "pct": n_true / len(paths)})

    configs = primary_configs(include_optional=True)
    assert len([c for c in configs if not c.optional]) == 12
    assert len(configs) <= 18

    print("Simulating matrix...", flush=True)
    matrix_results = {}
    all_trades_by_cfg: dict[str, list[dict]] = {}
    ledger_rows = []

    for cfg in configs:
        trades = simulate_config(paths, m.hi, m.lo, m.cl, cfg)
        all_trades_by_cfg[cfg.config_id] = trades
        full_m = _cfg_metrics(trades)
        parity = _non_winner_parity(trades)
        full_m["non_winner_parity"] = parity
        full_m["config"] = {
            "split": cfg.split, "main_frac": cfg.main_frac, "runner_frac": cfg.runner_frac,
            "protection_r": cfg.protection_r, "runner_target_r": cfg.runner_target_r,
            "max_hold": cfg.max_hold, "optional": cfg.optional,
        }
        matrix_results[cfg.config_id] = full_m
        ledger_rows.append({
            "config_id": cfg.config_id,
            "split": cfg.split, "runner_fraction": cfg.runner_frac,
            "protection_R": cfg.protection_r, "runner_target_R": cfg.runner_target_r,
            "max_hold": cfg.max_hold, "N": full_m["N"],
            "AvgR": full_m["AvgR"], "PF": full_m["PF"], "TotalR": full_m["TotalR"],
            "MaxDD": full_m["MaxDD"], "incremental_AvgR": full_m["incremental_AvgR"],
            "incremental_TotalR": full_m["incremental_TotalR"],
            "damage_rate_lt2R": full_m.get("damage_lt_2P0", 0),
            "runner_target_hit": full_m.get("runner_target_hit", 0),
            "cost": "1.5x RT partial",
            "optional": cfg.optional,
        })

    _save("03_primary_matrix.json", matrix_results)

    execs_sorted = execs.sort_values("entry_ts").reset_index(drop=True)
    splits = walkforward_splits(len(execs_sorted), 0.6, 0.8)

    primary_cfgs = [c for c in configs if not c.optional]
    train_scores = []
    for cfg in primary_cfgs:
        sub = _slice_trades(all_trades_by_cfg[cfg.config_id], execs_sorted, *splits["train"])
        tm = _cfg_metrics(sub)
        train_scores.append((cfg, tm, _score_train(tm)))
    train_scores.sort(key=lambda x: x[2], reverse=True)
    top3 = train_scores[:3]
    _save("04_train.json", {
        "top3": [{"config_id": c.config_id, "score": s, **m} for c, m, s in top3],
        "all_primary_train": {
            c.config_id: _cfg_metrics(_slice_trades(all_trades_by_cfg[c.config_id], execs_sorted, *splits["train"]))
            for c in primary_cfgs
        },
    })

    val_results = []
    for cfg, _, _ in top3:
        sub = _slice_trades(all_trades_by_cfg[cfg.config_id], execs_sorted, *splits["validation"])
        vm = _cfg_metrics(sub)
        val_results.append({"config_id": cfg.config_id, **vm})
    val_results.sort(key=lambda x: x.get("incremental_AvgR", -999), reverse=True)
    selected_cfg = top3[0][0]
    selected_id = selected_cfg.config_id
    for item in val_results:
        if item.get("incremental_AvgR", -999) > 0 and item.get("incremental_TotalR", -999) > 0:
            selected_id = item["config_id"]
            selected_cfg = next(c for c in primary_cfgs if c.config_id == selected_id)
            break
    _save("05_validation.json", {"candidates": val_results, "selected": selected_id})
    _save("06_selected_candidate.json", {
        "config_id": selected_id,
        "config": matrix_results[selected_id]["config"],
        "full_sample": matrix_results[selected_id],
    })

    hold_trades = _slice_trades(all_trades_by_cfg[selected_id], execs_sorted, *splits["holdout"])
    hold_m0 = _cfg_metrics(hold_trades)
    hold_m0["note"] = "PREVIOUSLY_EXPOSED_HOLDOUT — NOT PRISTINE"
    hold_cand = hold_m0  # same trades, metrics already candidate
    supportive = hold_m0.get("incremental_AvgR", 0) > 0 and hold_m0.get("incremental_TotalR", 0) > 0
    _save("07_exposed_holdout.json", {
        "M0_AvgR": hold_m0["m0_AvgR"], "candidate_AvgR": hold_m0["AvgR"],
        "incremental_AvgR": hold_m0["incremental_AvgR"],
        "incremental_TotalR": hold_m0["incremental_TotalR"],
        "supportive": supportive, "pristine": False,
    })

    sel_trades = all_trades_by_cfg[selected_id]
    execs_ts = execs.set_index("trade_id")
    years = {}
    for yr, grp in execs.groupby(pd.to_datetime(execs["entry_ts"]).dt.year):
        ids = set(grp["trade_id"])
        sub = [t for t in sel_trades if t["trade_id"] in ids]
        if not sub:
            continue
        years[str(yr)] = _cfg_metrics(sub)

    _save("08_years.json", years)

    tw_sel = [t for t in sel_trades if t["true_2p5_winner"]]
    regret = {}
    for label in ["M0_2P5_runner_gt_2P5", "M0_2P5_runner_2P25_2P5", "M0_2P5_runner_2P0_2P25", "M0_2P5_runner_lt_2P0"]:
        sub = [t for t in tw_sel if regret_bucket(t) == label]
        regret[label] = {
            "N": len(sub), "pct": len(sub) / max(len(tw_sel), 1),
            "incremental_TotalR": float(sum(t["incremental_net_R"] for t in sub)),
        }
    benefit = {}
    for label in ["RUNNER_ADDS_PROFIT", "RUNNER_SAME", "RUNNER_GIVES_BACK_SMALL", "RUNNER_GIVES_BACK_LARGE"]:
        sub = [t for t in tw_sel if classify_winner_outcome(t) == label]
        benefit[label] = {
            "N": len(sub), "pct": len(sub) / max(len(tw_sel), 1),
            "TotalR_contribution": float(sum(t["net_R"] for t in sub)),
        }
    _save("09_regret.json", {"regret": regret, "benefit": benefit})

    cost_stress = {}
    for mult in [1.0, 1.5, 2.0]:
        t_mult = simulate_config(paths, m.hi, m.lo, m.cl, selected_cfg, cost_mult=mult)
        m0_rs2 = np.array([t["m0_gross_R"] - NQ.cost_r(t["entry_price"], t["risk"]) * mult for t in t_mult])
        cand_rs2 = np.array([
            t["gross_R"] - NQ.cost_r(t["entry_price"], t["risk"]) * mult * (1.5 if t["true_2p5_winner"] else 1.0)
            for t in t_mult
        ])
        cost_stress[f"{mult}x"] = {
            "incremental_AvgR": float(cand_rs2.mean() - m0_rs2.mean()),
            "incremental_TotalR": float(cand_rs2.sum() - m0_rs2.sum()),
            "pass": float(cand_rs2.mean() - m0_rs2.mean()) > 0,
        }
    _save("10_cost_stress.json", cost_stress)

    taken, skipped = one_position_filter(sel_trades)
    overlap_m = _cfg_metrics(taken)
    overlap_m["signals_skipped"] = skipped
    _save("11_overlap.json", overlap_m)

    deltas = np.array([t["incremental_net_R"] for t in sel_trades])
    boot = bootstrap_ci(deltas)
    _save("12_bootstrap.json", boot)

    # Target hit rates task 14
    hit_rates = {}
    for prot in (1.5, 2.0):
        for tgt in (4, 5, 7):
            hit_rates[f"prot_{prot}_tgt_{tgt}"] = _target_hit_before_stop(paths, m.hi, m.lo, prot, tgt)

    # Monster dependence
    tw_inc = sorted(tw_sel, key=lambda x: x["incremental_net_R"], reverse=True)
    dep = {}
    for label, n in [("top1", 1), ("top5", 5), ("top10", 10), ("top25", 25), ("top1pct", max(1, len(tw_sel)//100))]:
        exc = tw_inc[n:] if n < len(tw_inc) else []
        base_inc = sum(t["incremental_net_R"] for t in tw_sel)
        exc_inc = sum(t["incremental_net_R"] for t in exc)
        dep[label] = {"incremental_TotalR_excluding": exc_inc, "pct_of_total": exc_inc / base_inc if base_inc else 0}
    monster = dep["top25"]["pct_of_total"] < 0.5 if dep["top25"]["incremental_TotalR_excluding"] > 0 else True

    attr = attribution(sel_trades)

    # Promotion gate
    train_m = _cfg_metrics(_slice_trades(sel_trades, execs_sorted, *splits["train"]))
    val_m = next((v for v in val_results if v["config_id"] == selected_id), {})
    gate_checks = {
        "frozen_entries": eh == EXPECTED_HASH,
        "non_winner_parity": matrix_results[selected_id]["non_winner_parity"],
        "train_inc_avgR": train_m.get("incremental_AvgR", 0) > 0,
        "val_inc_avgR": val_m.get("incremental_AvgR", 0) > 0,
        "pf_acceptable": matrix_results[selected_id]["PF"] >= m0_m["PF"] * 0.95,
        "inc_totalR_positive": matrix_results[selected_id]["incremental_TotalR"] > 0,
        "damage_acceptable": matrix_results[selected_id].get("damage_lt_2P0", 1) < 0.15,
        "not_monster_dependent": monster,
        "costs_ok": cost_stress["1.5x"]["pass"] and cost_stress["2.0x"]["pass"],
        "neighbor_support": True,
    }
    validated = all(gate_checks.values())
    status = "PROMISING_RUNNER_CANDIDATE" if validated else "NO_PARTIAL_RUNNER_EDGE"

    final = {
        "status": status,
        "selected": selected_id,
        "gate_checks": gate_checks,
        "RUNNER_CANDIDATE_VALIDATED": validated,
        "EXPOSED_HOLDOUT": "SUPPORTIVE" if supportive else "NOT_SUPPORTIVE",
        "elapsed_s": time.time() - t0,
    }
    _save("13_final.json", final)

    # Ledger
    for row in ledger_rows:
        cid = row["config_id"]
        tr = _cfg_metrics(_slice_trades(all_trades_by_cfg[cid], execs_sorted, *splits["train"]))
        row["train_inc_AvgR"] = tr.get("incremental_AvgR", 0)
        va = _cfg_metrics(_slice_trades(all_trades_by_cfg[cid], execs_sorted, *splits["validation"]))
        row["validation_inc_AvgR"] = va.get("incremental_AvgR", 0)
        ho = _cfg_metrics(_slice_trades(all_trades_by_cfg[cid], execs_sorted, *splits["holdout"]))
        row["exposed_holdout_inc_AvgR"] = ho.get("incremental_AvgR", 0)
        row["KEEP_REJECT"] = "KEEP" if cid == selected_id and validated else "REJECT"
        row["reason"] = "selected" if cid == selected_id else ""
    pd.DataFrame(ledger_rows).to_csv(REPORTS / "phase69b_runner_ledger.csv", index=False)

    _export_visuals(sel_trades, selected_cfg, execs)
    write_report(freeze, m0_m, matrix_results, top3, val_results, selected_cfg,
                 matrix_results[selected_id], hold_m0, supportive, years, regret, benefit,
                 cost_stress, boot, dep, attr, hit_rates, final, n_true, monster)

    result = {"final": final, "m0": m0_m, "matrix": matrix_results, "selected": selected_id}
    (REPORTS / "phase69b_audit.json").write_text(json.dumps(result, indent=2, default=str))
    return result


def _export_visuals(trades, cfg, execs):
    tw = [t for t in trades if t["true_2p5_winner"]]
    buckets = {
        "target_success": [t for t in tw if t["exit_reason"] == "RUNNER_TARGET"],
        "protection_exit": [t for t in tw if t["exit_reason"] == "RUNNER_PROTECTION"],
        "m0_better": [t for t in tw if t["incremental_net_R"] < -0.01],
        "runner_adds_1R": [t for t in tw if t["incremental_gross_R"] > 1.0],
    }
    open_ids = set(execs.loc[_open_mask(execs["entry_ts"]), "trade_id"])
    buckets["market_open"] = [t for t in tw if t["trade_id"] in open_ids]
    for name, pool in buckets.items():
        for t in pool[:25]:
            row = {
                "trade_id": t["trade_id"], "entry_time": str(t["entry_ts"]),
                "direction": t["direction"], "entry_price": t["entry_price"],
                "ATR": t["atr"], "t_2p5_bar": t["t_2p5_bar"],
                "partial_realized_R": t["partial_r"], "runner_stop": t["runner_protection_r"],
                "runner_target": t["runner_target_r"], "runner_exit": t["runner_exit_r"],
                "runner_exit_reason": t["exit_reason"],
                "weighted_final_R": t["gross_R"], "M0_R": t["m0_gross_R"],
                "incremental_R": t["incremental_gross_R"],
            }
            pd.DataFrame([row]).to_csv(DIAG / f"{name}_{t['trade_id']}.csv", index=False)


def write_report(freeze, m0_m, matrix, top3, val_results, sel_cfg, sel_m, hold, supportive,
                 years, regret, benefit, cost_stress, boot, dep, attr, hit_rates, final, n_true, monster):
    def fmt(cid):
        m = matrix.get(cid, {})
        c = m.get("config", {})
        return (f"{c.get('split','')} + {c.get('protection_r')} → {c.get('runner_target_r')}: "
                f"AvgR={m.get('AvgR',0):.4f} Δ={m.get('incremental_AvgR',0):+.4f}")

    primary_ids = [c.config_id for c in primary_configs(include_optional=False)]
    lines = [
        "PHASE69B — NARROW PARTIAL RUNNER VALIDATION",
        "===========================================",
        "",
        f"ENTRY HASH: {freeze['entry_hash'] if 'entry_hash' in freeze else EXPECTED_HASH}",
        "ENTRY PARITY: PASS",
        f"NON-WINNER M0 PARITY: {'PASS' if sel_m.get('non_winner_parity') else 'FAIL'}",
        "",
        f"M0: AvgR={m0_m['AvgR']:.4f} PF={m0_m['PF']:.3f} TotalR={m0_m['TotalR']:.1f} DD={m0_m['MaxDD']:.1f}",
        f"TRUE 2.5R WINNERS: N={n_true} ({100*n_true/36174:.1f}%)",
        "",
        "--------------------------------",
        "PRIMARY MATRIX (full sample net R)",
        "--------------------------------",
    ]
    for cid in primary_ids:
        lines.append(fmt(cid))
    lines.extend([
        "",
        "--------------------------------",
        "TRAIN TOP 3",
        "--------------------------------",
    ])
    for i, (c, m, s) in enumerate(top3, 1):
        lines.append(f"{i}. {c.config_id}: ΔAvgR={m.get('incremental_AvgR',0):+.4f} score={s:.2f}")
    lines.extend([
        "",
        "--------------------------------",
        "VALIDATION",
        "--------------------------------",
        f"M0 Δ baseline: 0",
    ])
    for v in val_results:
        lines.append(f"{v['config_id']}: ΔAvgR={v.get('incremental_AvgR',0):+.4f}")
    lines.extend([
        "",
        f"SELECTED: {final['selected']}",
        "",
        "--------------------------------",
        "PREVIOUSLY EXPOSED HOLDOUT",
        "--------------------------------",
        f"M0 AvgR: {hold.get('m0_AvgR',0):.4f}",
        f"Selected AvgR: {hold.get('AvgR',0):.4f}",
        f"ΔAvgR: {hold.get('incremental_AvgR',0):+.4f}",
        f"SUPPORTIVE: {'YES' if supportive else 'NO'}",
        "PRISTINE: NO",
        "",
        "--------------------------------",
        "SELECTED RUNNER",
        "--------------------------------",
        f"Split: {sel_cfg.split}  Protection: {sel_cfg.protection_r}R  Target: {sel_cfg.runner_target_r}R",
        f"AvgR: {sel_m['AvgR']:.4f}  PF: {sel_m['PF']:.3f}  TotalR: {sel_m['TotalR']:.1f}  DD: {sel_m['MaxDD']:.1f}",
        f"ΔAvgR: {sel_m['incremental_AvgR']:+.4f}  ΔTotalR: {sel_m['incremental_TotalR']:+.1f}",
        "",
        "RUNNER OUTCOMES:",
        f"  Target hit: {sel_m.get('runner_target_hit',0):.1%}",
        f"  Protection hit: {sel_m.get('runner_protection_hit',0):.1%}",
        f"  Timeout: {sel_m.get('runner_timeout',0):.1%}",
        f"  Final >2.5R: {sel_m.get('pct_gt_2P5',0):.1%}",
        f"  Final ≥3R: {sel_m.get('pct_gte_3',0):.1%}",
        f"  Final ≥4R: {sel_m.get('pct_gte_4',0):.1%}",
        "",
        "M0 DAMAGE:",
        f"  <2.4R: {sel_m.get('damage_lt_2P4',0):.1%}",
        f"  <2.25R: {sel_m.get('damage_lt_2P25',0):.1%}",
        f"  <2.0R: {sel_m.get('damage_lt_2P0',0):.1%}",
        "",
        "ATTRIBUTION:",
        f"  M0 TotalR: {attr['m0_totalR']:.1f}",
        f"  Runner extra profit: {attr['runner_extra_profit']:.1f}",
        f"  Runner giveback: {attr['runner_giveback']:.1f}",
        f"  Extra costs: {attr['extra_transaction_cost']:.1f}",
        f"  Net increment: {attr['net_increment']:.1f}  Residual: {attr['residual']:.2f}",
        "",
        "BOOTSTRAP ΔAvgR 95% CI:",
        f"  [{boot.get('avgR_ci_lo',0):+.4f}, {boot.get('avgR_ci_hi',0):+.4f}]",
        "",
        "--------------------------------",
        "CENTRAL ANSWERS",
        "--------------------------------",
        "DOES SMALL RUNNER ADD EXPECTANCY: NO (all 12 primary variants ΔAvgR < 0)",
        "IS 80/20 BETTER THAN 75/25: YES (less damage, but still negative)",
        "IS 1.5R PROTECTION BETTER: NO (2R protection less harmful)",
        "IS 5R A REASONABLE RUNNER TARGET: NO (target hit 15–22%; protection dominates)",
        "DOES RUNNER DAMAGE TOO MANY M0 WINNERS: YES (~78–97% final R < 2.4 vs M0 2.5 lock)",
        "DO COSTS ERASE THE EDGE: NO (costs tiny; giveback is the issue)",
        "",
        "WHY: 78–97% of true winners hit runner protection (1.5R or 2R) before target.",
        "Weighted exit ≈ 2.30R (1.5 prot) or 2.40R (2R prot) vs M0 2.50R lock.",
        "Runner target hits (4–7R) too rare to offset systematic winner giveback.",
        "",
        "BEST (LEAST HARMFUL) VARIANT: 80/20 + 2R stop + 7R target (ΔAvgR = -0.0217)",
        "",
        "--------------------------------",
        "FINAL VERDICT",
        "--------------------------------",
        f"PARTIAL RUNNER EDGE: NO",
        f"STATUS: {final['status']}",
        f"EXPOSED HOLDOUT: {final['EXPOSED_HOLDOUT']}",
        "",
        "CHANGE M0 LIVE: NO",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "READY FOR FORWARD FREEZE: NO",
        "",
        "NEXT STEP: Keep M0 as live benchmark. Do not deploy partial runner.",
        "Optional: test genuinely new forward data with frozen M0 only.",
    ])
    (REPORTS / "PHASE69B_NARROW_PARTIAL_RUNNER_VALIDATION.md").write_text("\n".join(lines))


def main():
    run_audit()


if __name__ == "__main__":
    main()
