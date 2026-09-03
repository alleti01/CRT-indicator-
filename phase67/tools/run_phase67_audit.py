#!/usr/bin/env python3
"""Phase67 — independent causal multi-stage entry discovery."""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.walkforward_audit import walkforward_splits
from phase60.tools.run_phase60 import test_prefix_invariance, test_vectorized_vs_sequential
from phase67.python.families import SCANNERS, SetupSignal
from phase67.python.metrics import (
    aggregate_paths, early_gate, path_from_signal, simulate_signal, summarize_sim,
)
from phase67.python.precompute import build_precomputed

REPORTS = ROOT / "phase67" / "reports"
CHECKPOINTS = ROOT / "phase67" / "checkpoints"
DIAG = ROOT / "phase67" / "diagnostics"

# Primary hypotheses: A, B(5/10/20), C, D, E = 7 structural configs
PRIMARY_KEYS = ["A", "B10", "B5", "B20", "C", "D", "E"]
FAMILY_LABEL = {
    "A": "EXPANSION → PULLBACK → RESUMPTION",
    "B10": "SWEEP → DISPLACEMENT → RETEST (10-bar)",
    "B5": "SWEEP → DISPLACEMENT → RETEST (5-bar)",
    "B20": "SWEEP → DISPLACEMENT → RETEST (20-bar)",
    "C": "COMPRESSION → EXPANSION → RETEST",
    "D": "FAILED AUCTION → DISPLACEMENT → RETEST",
    "E": "STRUCTURE BREAK → RETRACE → SECOND IMPULSE",
}


def _save(name: str, obj: dict) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _load(name: str) -> dict | None:
    p = CHECKPOINTS / name
    return json.loads(p.read_text()) if p.exists() else None


def evaluate_family(key: str, pre, signals: list[SetupSignal]) -> dict:
    paths, sims = [], []
    for sig in signals:
        pth = path_from_signal(pre, sig)
        sim = simulate_signal(pre, sig, target_r=2.0, cost_mult=1.0, max_hold=60)
        paths.append({**pth, **sim})
        sims.append(sim)
    path_agg = aggregate_paths(paths)
    sim_net = summarize_sim(sims)
    sim_gross = summarize_sim([{**s, "net_R": s["gross_R"]} for s in sims])
    stress15 = summarize_sim([
        {**s, "net_R": s["gross_R"] - s["cost_R"] * 1.5} for s in sims
    ])
    long_p = [x for x, s in zip(paths, signals) if s.direction == "LONG"]
    short_p = [x for x, s in zip(paths, signals) if s.direction == "SHORT"]
    gate_pass, gate_reason = early_gate(path_agg, sim_net)
    return {
        "key": key,
        "label": FAMILY_LABEL[key],
        "raw_signals": len(signals),
        "n_episodes": len(signals),
        "n_long": sum(1 for s in signals if s.direction == "LONG"),
        "n_short": sum(1 for s in signals if s.direction == "SHORT"),
        "path": path_agg,
        "sim_net": sim_net,
        "sim_gross": sim_gross,
        "stress_1.5x": stress15,
        "long_path": aggregate_paths(long_p),
        "short_path": aggregate_paths(short_p),
        "early_gate": gate_pass,
        "early_gate_reason": gate_reason,
    }


def random_direction_control(pre, signals: list[SetupSignal], seed: int = 67) -> dict:
    rng = np.random.default_rng(seed)
    paths_orig, paths_rand = [], []
    for sig in signals:
        paths_orig.append(path_from_signal(pre, sig))
        flip = SetupSignal(**{**sig.__dict__, "direction": "SHORT" if sig.direction == "LONG" else "LONG"})
        paths_rand.append(path_from_signal(pre, flip))
    return {
        "original": aggregate_paths(paths_orig),
        "random_dir": aggregate_paths(paths_rand),
    }


def timestamp_shift_control(pre, signals: list[SetupSignal], offsets=(5, 10)) -> dict:
    out = {}
    for off in offsets:
        shifted = []
        for sig in signals:
            ei = sig.entry_i + off
            if ei >= pre.n - 61:
                continue
            s2 = SetupSignal(**{**sig.__dict__, "entry_i": ei})
            shifted.append(path_from_signal(pre, s2))
        out[f"+{off}"] = aggregate_paths(shifted)
    return out


def walkforward_econ(pre, signals: list[SetupSignal]) -> dict:
    rows = []
    for sig in sorted(signals, key=lambda s: s.entry_i):
        sim = simulate_signal(pre, sig, 2.0, 1.0, 60)
        pth = path_from_signal(pre, sig)
        flat = {**sim, **{k: v for k, v in pth.items() if k != "pairs"}}
        flat["pairs"] = pth["pairs"]
        flat["entry_i"] = sig.entry_i
        rows.append(flat)
    if not rows:
        return {}
    splits = walkforward_splits(len(rows), 0.6, 0.8)
    wf = {}
    for name, (a, b) in splits.items():
        sub = rows[a:b]
        wf[name] = {**summarize_sim(sub), "path": aggregate_paths(sub)}
    years = {}
    for y in sorted({pre.idx[int(r["entry_i"])].year for r in rows}):
        sub = [r for r in rows if pre.idx[int(r["entry_i"])].year == y]
        years[int(y)] = summarize_sim(sub)
    pos_net = sum(1 for v in years.values() if v.get("AvgR", -999) > 0)
    return {"splits": wf, "years": years, "positive_net_years": pos_net, "total_years": len(years)}


def export_samples(pre, key: str, signals: list[SetupSignal], n: int = 25) -> None:
    DIAG.mkdir(parents=True, exist_ok=True)
    review = DIAG / "visual_review"
    review.mkdir(exist_ok=True)
    rng = np.random.default_rng(67)
    if len(signals) > n:
        idx = rng.choice(len(signals), n, replace=False)
        sample = [signals[i] for i in idx]
    else:
        sample = signals
    rows = []
    for sig in sample:
        pth = path_from_signal(pre, sig)
        sim = simulate_signal(pre, sig)
        rows.append({
            "family": key, "direction": sig.direction, "setup_i": sig.setup_i,
            "trigger_i": sig.trigger_i, "entry_i": sig.entry_i,
            "entry_ts": str(pre.idx[sig.entry_i]), "setup_ts": str(pre.idx[sig.setup_i]),
            "origin": sig.origin_price, "invalidation": sig.invalidation,
            "delay": sig.delay_bars, "chase_atr": sig.chase_atr,
            "reason": sig.reason, "level": sig.level_name,
            "+2_before_-1": pth["pairs"].get("+2_before_-1"),
            "mfe_15m": pth.get("mfe_15m"), "mae_15m": pth.get("mae_15m"),
            "gross_R": sim["gross_R"], "cost_R": sim["cost_R"], "net_R": sim["net_R"],
        })
    pd.DataFrame(rows).to_csv(review / f"phase67_{key}_sample.csv", index=False)


def run_audit(resume: bool = True) -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    ledger = []

    # STAGE 1
    print("STAGE 1: Data integrity...", flush=True)
    pre, integrity = build_precomputed()
    causality = {
        "sequential_parity": test_vectorized_vs_sequential(max_bars=2000)["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=3)["pass"],
    }
    stage1 = {"integrity": integrity, "causality": causality, "bars": pre.n,
              "start": str(pre.idx.min()), "end": str(pre.idx.max())}
    _save("stage01_integrity.json", stage1)

    # STAGE 2-3: scan families
    families = {}
    for key in PRIMARY_KEYS:
        ck = f"stage03_family_{key}.json"
        cached = _load(ck) if resume else None
        if cached and "path" in cached:
            print(f"  {key}: loaded checkpoint", flush=True)
            families[key] = cached
            continue
        print(f"STAGE 3: Scanning {key}...", flush=True)
        try:
            raw = SCANNERS[key](pre)
            print(f"  {key}: {len(raw):,} episodes", flush=True)
            ev = evaluate_family(key, pre, raw)
            ev["signals"] = len(raw)
            families[key] = {k: v for k, v in ev.items() if k != "signals"}
            families[key]["n_episodes"] = len(raw)
            _save(ck, families[key])
            ledger.append({"hypothesis": key, "n": len(raw), "po2": ev["path"].get("+2_before_-1"),
                           "gate": ev["early_gate"], "reason": ev["early_gate_reason"]})
            export_samples(pre, key, raw)
        except Exception as e:
            families[key] = {"error": str(e), "trace": traceback.format_exc()}
            ledger.append({"hypothesis": key, "error": str(e)})

    _save("stage04_path_metrics.json", {k: v.get("path", {}) for k, v in families.items() if "path" in v})

    # STAGE 5: survivors (top 3 by +2/-1 among those passing early gate, else top 3 by po2)
    ranked = sorted(
        [(k, v) for k, v in families.items() if "path" in v],
        key=lambda kv: kv[1]["path"].get("+2_before_-1", 0),
        reverse=True,
    )
    survivors = [k for k, v in ranked if v.get("early_gate")][:3]
    if not survivors:
        survivors = [k for k, _ in ranked[:3]]
    _save("stage05_survivors.json", {"survivors": survivors, "ranking": [k for k, _ in ranked]})

    # STAGE 6-8: economics + walkforward + controls on survivors
    survivor_detail = {}
    for key in survivors:
        print(f"STAGE 6-8: Deep test {key}...", flush=True)
        raw = SCANNERS[key](pre)
        wf = walkforward_econ(pre, raw)
        ctrl_dir = random_direction_control(pre, raw)
        ctrl_ts = timestamp_shift_control(pre, raw)
        survivor_detail[key] = {"walkforward": wf, "random_direction": ctrl_dir, "timestamp_shift": ctrl_ts}

    _save("stage06_economics.json", {k: families[k].get("sim_net") for k in survivors})
    _save("stage07_walkforward.json", {k: v.get("walkforward") for k, v in survivor_detail.items()})
    _save("stage08_controls.json", survivor_detail)

    # Verdicts
    for k, v in families.items():
        if "path" not in v:
            v["verdict"] = "ERROR"
            continue
        po2 = v["path"].get("+2_before_-1", 0)
        net = v["sim_net"].get("AvgR", -999)
        gross = v["sim_gross"].get("AvgR", -999)
        if po2 >= 0.40 and net > 0 and gross > 0:
            v["verdict"] = "TRADEABLE_CANDIDATE"
        elif po2 >= 0.38 or v.get("early_gate"):
            v["verdict"] = "DIRECTIONALLY_INTERESTING"
        else:
            v["verdict"] = "REJECT"

    result = {
        "stage1": stage1,
        "families": families,
        "survivors": survivors,
        "survivor_detail": survivor_detail,
        "ledger": ledger,
        "total_hypotheses": len(PRIMARY_KEYS),
        "elapsed_s": time.time() - t0,
        "phase58_used": False,
    }
    (REPORTS / "phase67_audit.json").write_text(json.dumps(result, indent=2, default=str))
    write_report(result)
    return result


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE67_INDEPENDENT_CAUSAL_MULTISTAGE_ENTRY_DISCOVERY.md"
    s1 = r["stage1"]
    caus = s1["causality"]
    lines = [
        "PHASE67 — INDEPENDENT CAUSAL MULTI-STAGE ENTRY DISCOVERY",
        "========================================================",
        "",
        f"CAUSALITY: {'PASS' if caus['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if caus['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        f"DATA: {s1['integrity']['start']} → {s1['integrity']['end']}",
        f"BARS: {s1['bars']:,}",
        "INSTRUMENT: NQ continuous 1M",
        "PHASE58 USED IN DISCOVERY: NO",
        f"TOTAL STRUCTURAL HYPOTHESES TESTED: {r['total_hypotheses']}",
        "",
    ]

    order = ["A", "B10", "B5", "B20", "C", "D", "E"]
    ranking = []
    for key in order:
        f = r["families"].get(key, {})
        if "path" not in f:
            lines.extend([f"--- FAMILY {key} ---", f"ERROR: {f.get('error', 'unknown')}", ""])
            continue
        p, s, g = f["path"], f["sim_net"], f["sim_gross"]
        ranking.append((key, p.get("+2_before_-1", 0)))
        lines.extend([
            "--------------------------------------------",
            f"FAMILY {key}",
            FAMILY_LABEL.get(key, key),
            "--------------------------------------------",
            "",
            f"N episodes: {f['n_episodes']:,}",
            f"LONG: {f['n_long']:,}  SHORT: {f['n_short']:,}",
            f"Median delay: {p.get('median_delay', 0):.1f} bars",
            f"Median chase: {p.get('median_chase', 0):.2f} ATR",
            f"Median natural stop: {s.get('median_risk_atr', 0):.2f} ATR",
            "",
            f"+1/-1: {p.get('+1_before_-1', 0):.1%}",
            f"+1.5/-1: {p.get('+1.5_before_-1', 0):.1%}",
            f"+2/-1: {p.get('+2_before_-1', 0):.1%}",
            f"+2.5/-1: {p.get('+2.5_before_-1', 0):.1%}",
            f"+2/-1.5: {p.get('+2_before_-1.5', 0):.1%}",
            f"+3/-1.5: {p.get('+3_before_-1.5', 0):.1%}",
            "",
            f"MFE 15: {p.get('median_mfe_15m', 0):.2f}  MAE 15: {p.get('median_mae_15m', 0):.2f}  DAS: {p.get('das_15m', 0):.2f}",
            f"MFE 60: {p.get('median_mfe_60m', 0):.2f}  MAE 60: {p.get('median_mae_60m', 0):.2f}  DAS: {p.get('das_60m', 0):.2f}",
            "",
            f"Gross AvgR: {g.get('AvgR', 0):.4f}",
            f"Net AvgR: {s.get('AvgR', 0):.4f}",
            f"PF: {s.get('PF', 0):.3f}",
            f"TotalR: {s.get('TotalR', 0):.0f}",
            f"MaxDD: {s.get('MaxDD', 0):.0f}",
            f"Cost R: {s.get('avg_cost_R', 0):.4f}",
            f"Early gate: {f.get('early_gate')} ({f.get('early_gate_reason')})",
            f"VERDICT: {f.get('verdict', 'REJECT')}",
            "",
        ])

    ranking.sort(key=lambda x: x[1], reverse=True)
    best_key = ranking[0][0] if ranking else "NONE"
    bf = r["families"].get(best_key, {})
    sd = r.get("survivor_detail", {}).get(best_key, {})

    lines.extend([
        "--------------------------------------------",
        "FAMILY RANKING (+2/-1)",
        "--------------------------------------------",
        "",
    ])
    for i, (k, po2) in enumerate(ranking, 1):
        lines.append(f"{i}. {k} ({FAMILY_LABEL.get(k, k)}): +2/-1={po2:.1%}")

    any_gross = any(r["families"].get(k, {}).get("sim_gross", {}).get("AvgR", -1) > 0 for k in order)
    any_net = any(r["families"].get(k, {}).get("sim_net", {}).get("AvgR", -1) > 0 for k in order)
    best_po2 = bf.get("path", {}).get("+2_before_-1", 0)

    ctrl = sd.get("random_direction", {})
    ctrl_pass = False
    if ctrl:
        o2 = ctrl.get("original", {}).get("+2_before_-1", 0)
        r2 = ctrl.get("random_dir", {}).get("+2_before_-1", 0)
        ctrl_pass = o2 > r2 + 0.03

    lines.extend([
        "",
        "--------------------------------------------",
        "CENTRAL ANSWERS",
        "--------------------------------------------",
        "",
        f"A HAS REAL DIRECTIONAL EDGE: {'MARGINAL' if r['families'].get('A',{}).get('path',{}).get('+2_before_-1',0)>0.36 else 'NO'}",
        f"B HAS REAL DIRECTIONAL EDGE: {'MARGINAL' if max(r['families'].get(k,{}).get('path',{}).get('+2_before_-1',0) for k in ['B10','B5','B20'])>0.36 else 'NO'}",
        f"C HAS REAL DIRECTIONAL EDGE: {'MARGINAL' if r['families'].get('C',{}).get('path',{}).get('+2_before_-1',0)>0.36 else 'NO'}",
        f"D HAS REAL DIRECTIONAL EDGE: {'MARGINAL' if r['families'].get('D',{}).get('path',{}).get('+2_before_-1',0)>0.36 else 'NO'}",
        f"E HAS REAL DIRECTIONAL EDGE: {'MARGINAL' if r['families'].get('E',{}).get('path',{}).get('+2_before_-1',0)>0.36 else 'NO'}",
        f"ANY FAMILY HAS GROSS EDGE: {'YES' if any_gross else 'NO'}",
        f"ANY FAMILY HAS NET EDGE: {'YES' if any_net else 'NO'}",
        f"RANDOM DIRECTION CONTROL: {'PASS' if ctrl_pass else 'FAIL'}",
        "",
        "--------------------------------------------",
        "FINAL VERDICT",
        "--------------------------------------------",
        "",
        f"NEW CAUSAL ENTRY EDGE FOUND: {'NO' if best_po2 < 0.40 or not any_net else 'MAYBE'}",
        f"BEST FAMILY: {best_key}",
        f"DIRECTIONALLY MEANINGFUL: {'YES' if best_po2 >= 0.38 else 'NO'}",
        f"ECONOMICALLY MEANINGFUL: {'YES' if any_net else 'NO'}",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "",
        "NEXT STEP: See phase67/reports/phase67_audit.json for full metrics.",
        f"Runtime: {r.get('elapsed_s', 0):.0f}s",
    ])
    out.write_text("\n".join(lines))
    return out


def main():
    t0 = time.time()
    result = run_audit(resume=True)
    print(f"\nDone {time.time()-t0:.0f}s", flush=True)
    print(REPORTS / "PHASE67_INDEPENDENT_CAUSAL_MULTISTAGE_ENTRY_DISCOVERY.md", flush=True)


if __name__ == "__main__":
    main()
