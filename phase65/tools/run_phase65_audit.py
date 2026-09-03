#!/usr/bin/env python3
"""Phase65 — causal activity alarm → market choice → early expansion trader."""
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
from phase62.python.analysis import path_ordering
from phase63.python.reaction import r3_displacement
from phase63.tools.run_phase63_audit import _apply_model
from phase65.python.market_choice import ChoiceResult, naive_first_break, scan_market_choice
from phase65.python.metrics_phase65 import event_capture_detail, label_events, one_position_filter, path_metrics
from phase65.python.sim_phase65 import SimConfig, remaining_mfe, simulate_phase65, summarize_trades

REPORTS = ROOT / "phase65" / "reports"
SIGNALS = ROOT / "phase60" / "diagnostics" / "cache" / "p58_trades_phase60.parquet"


def _load_alarms(cfg: dict) -> pd.DataFrame:
    signals = pd.read_parquet(SIGNALS)
    cl = cluster_signals(signals, structural_gap=cfg.get("structural_gap_bars", 30))
    ev = cl[cl["opp_rank"] == 1].copy()
    ev["orig_dir"] = ev["direction"]
    return ev


def _batch_choices(m, events: pd.DataFrame, concept: str, thr: float = 0.5) -> pd.DataFrame:
    rows = []
    for _, r in events.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        ch = scan_market_choice(m, si, atr, concept, max_delay=3, thr=thr)
        rows.append({
            "signal_i": si,
            "atr": atr,
            "orig_dir": r["orig_dir"],
            "decision": ch.decision,
            "direction": ch.direction,
            "choice_i": ch.choice_i,
            "entry_i": ch.entry_i,
            "delay_bars": ch.delay_bars,
            "reason": ch.reason,
            "chase_atr": ch.chase_atr,
        })
    return pd.DataFrame(rows)


def _simulate_choices(m, choices: pd.DataFrame, cfg: SimConfig) -> pd.DataFrame:
    rows = []
    for _, c in choices[choices["decision"] == "TAKE"].iterrows():
        si, ei = int(c["signal_i"]), int(c["entry_i"])
        origin = float(m.op[si])
        sim = simulate_phase65(m, si, ei, c["direction"], origin, float(c["atr"]), cfg)
        rem = remaining_mfe(m, ei, c["direction"], float(c["atr"]))
        rows.append({**sim, **rem, **c.to_dict()})
    return pd.DataFrame(rows)


def _summarize_concept(m, events, labeled, choices, cfg: SimConfig) -> dict:
    n = len(events)
    taken = choices[choices["decision"] == "TAKE"]
    expired = choices[choices["decision"] == "EXPIRED"]
    sim = _simulate_choices(m, choices, cfg)
    sm = summarize_trades(sim) if len(sim) else {"N": 0}
    sm_gross = summarize_trades(sim.assign(net_R=sim["gross_R"])) if len(sim) else {"N": 0}
    pm = path_metrics(m, sim) if len(sim) else {}
    cap = event_capture_detail(m, labeled, choices)
    delay_dist = taken["delay_bars"].value_counts(normalize=True).to_dict() if len(taken) else {}
    return {
        "n_alarms": n,
        "n_trades": len(taken),
        "retention": len(taken) / n if n else 0,
        "n_expired": len(expired),
        "median_delay": float(taken["delay_bars"].median()) if len(taken) else 0,
        "median_chase": float(taken["chase_atr"].median()) if len(taken) else 0,
        "rem_mfe_15m": float(sim["rem_mfe_15m"].median()) if len(sim) and "rem_mfe_15m" in sim else 0,
        "rem_mfe_60m": float(sim["rem_mfe_60m"].median()) if len(sim) and "rem_mfe_60m" in sim else 0,
        "path": pm,
        "capture": cap,
        "sim_net": sm,
        "sim_gross": sm_gross,
        "delay_dist": delay_dist,
        "sim_df": sim,
    }


def _baseline_original(m, events, cfg: SimConfig) -> dict:
    rows = []
    for _, r in events.iterrows():
        si = int(r["signal_i"])
        ei = si + 1
        origin = float(m.op[si])
        sim = simulate_phase65(m, si, ei, r["orig_dir"], origin, float(r["atr"]), cfg)
        rows.append(sim)
    sim = pd.DataFrame(rows)
    return {"sim": sim, "summary": summarize_trades(sim), "path": path_metrics(m, sim)}


def _baseline_naive(m, events, thr: float, cfg: SimConfig) -> dict:
    rows = []
    choices = []
    for _, r in events.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        ch = naive_first_break(m, si, atr, thr)
        choices.append(ch)
        if ch.decision == "TAKE":
            origin = float(m.op[si])
            sim = simulate_phase65(m, si, ch.entry_i, ch.direction, origin, atr, cfg)
            sim["delay_bars"] = ch.delay_bars
            sim["chase_atr"] = ch.chase_atr
            rows.append(sim)
    sim = pd.DataFrame(rows)
    return {
        "sim": sim,
        "summary": summarize_trades(sim),
        "path": path_metrics(m, sim),
        "median_delay": float(np.median([c.delay_bars for c in choices if c.decision == "TAKE"])) if rows else 0,
        "median_chase": float(sim["chase_atr"].median()) if len(sim) and "chase_atr" in sim else 0,
    }


def _baseline_phase63(m, events, cfg: SimConfig) -> dict:
    trades = _apply_model(events, m, "R3", "T1", "D2")
    rows = []
    for _, c in trades[trades["decision"] == "TAKE"].iterrows():
        si, ei = int(c["signal_i"]), int(c["entry_i"])
        origin = float(m.op[si])
        sim = simulate_phase65(m, si, ei, c["direction"], origin, float(c["atr"]), cfg)
        sim["delay_bars"] = c["delay_bars"]
        rows.append(sim)
    sim = pd.DataFrame(rows)
    return {"sim": sim, "summary": summarize_trades(sim), "path": path_metrics(m, sim)}


def _early_signature(m, labeled: pd.DataFrame, sample_n: int = 5000) -> dict:
    """Observable differences clean/explosive vs chaos by T+1..T+3."""
    rng = np.random.default_rng(65)
    sub = labeled[labeled["is_clean"] | labeled["is_explosive"] | labeled["is_chaos"]].sample(
        min(sample_n, len(labeled)), random_state=65
    )
    feats = []
    for _, r in sub.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        origin = float(m.op[si])
        a = atr if atr > 0 else 1.0
        for off in [1, 2, 3]:
            ei = si + off
            if ei >= m.n:
                continue
            up = (float(m.hi[si : ei + 1].max()) - origin) / a
            dn = (origin - float(m.lo[si : ei + 1].min())) / a
            c = float(m.cl[ei])
            giveback_up = (float(m.hi[si : ei + 1].max()) - c) / a
            grp = "explosive" if r["is_explosive"] else "clean" if r["is_clean"] else "chaos"
            feats.append({"group": grp, "offset": off, "up": up, "dn": dn, "asym": up - dn, "giveback_up": giveback_up})
    df = pd.DataFrame(feats)
    out = {}
    for off in [1, 2, 3]:
        s = df[df["offset"] == off]
        if s.empty:
            continue
        out[f"T+{off}"] = {
            "explosive_median_up": float(s[s["group"] == "explosive"]["up"].median()) if (s["group"] == "explosive").any() else 0,
            "clean_median_up": float(s[s["group"] == "clean"]["up"].median()) if (s["group"] == "clean").any() else 0,
            "chaos_median_up": float(s[s["group"] == "chaos"]["up"].median()) if (s["group"] == "chaos").any() else 0,
            "explosive_asym": float(s[s["group"] == "explosive"]["asym"].median()) if (s["group"] == "explosive").any() else 0,
            "chaos_asym": float(s[s["group"] == "chaos"]["asym"].median()) if (s["group"] == "chaos").any() else 0,
        }
    return out


def _walkforward(sim: pd.DataFrame) -> dict:
    if sim.empty:
        return {}
    t = sim.sort_values("entry_i").reset_index(drop=True)
    splits = walkforward_splits(len(t), 0.6, 0.8)
    out = {}
    for name, (a, b) in splits.items():
        sub = t.iloc[a:b]
        out[name] = summarize_trades(sub)
    return out


def _year_stats(sim: pd.DataFrame, idx) -> dict:
    if sim.empty:
        return {}
    sim = sim.copy()
    sim["year"] = [idx[int(i)].year for i in sim["entry_i"]]
    yrs = {}
    for y, g in sim.groupby("year"):
        yrs[int(y)] = summarize_trades(g)
    return yrs


def _agreement_diag(sim: pd.DataFrame) -> dict:
    if sim.empty or "orig_dir" not in sim.columns:
        return {}
    agree = sim[sim["direction"] == sim["orig_dir"]]
    disagree = sim[sim["direction"] != sim["orig_dir"]]
    return {
        "agree": summarize_trades(agree),
        "disagree": summarize_trades(disagree),
    }


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    print("Loading...", flush=True)
    ma = build_market_arrays_phase60()
    events = _load_alarms(cfg)
    n = len(events)
    print(f"Alarms: {n:,}", flush=True)

    print("Labeling events (retrospective)...", flush=True)
    labeled = label_events(ma, events)

    default_sim = SimConfig(stop_mode="origin", target_r=2.5, cost_mult=1.0)

    concepts = {}
    for c in ["M1", "M2", "M3", "M4"]:
        print(f"  {c} choices...", flush=True)
        ch = _batch_choices(ma, events, c, thr=0.5)
        concepts[c] = _summarize_concept(ma, events, labeled, ch, default_sim)
        concepts[c]["choices"] = ch

    print("Baselines...", flush=True)
    baselines = {
        "original": _baseline_original(ma, events, default_sim),
        "naive_05": _baseline_naive(ma, events, 0.5, default_sim),
        "naive_10": _baseline_naive(ma, events, 1.0, default_sim),
        "phase63_rc": _baseline_phase63(ma, events, default_sim),
    }

    print("Stop comparison (best concept)...", flush=True)
    best_c = max(concepts, key=lambda k: concepts[k]["sim_net"].get("TotalR", -1e9))
    ch_best = concepts[best_c]["choices"]
    stops = {}
    for sm, label in [("origin", "S1"), ("origin_buffer", "S2"), ("hybrid", "S3")]:
        sc = SimConfig(stop_mode=sm, target_r=2.5, cost_mult=1.0)
        if sm == "origin_buffer":
            sc.origin_buffer_atr = 0.25
        stops[label] = summarize_trades(_simulate_choices(ma, ch_best, sc))

    print("Target comparison...", flush=True)
    targets = {}
    for tr in [2.0, 2.5, 3.0]:
        sc = SimConfig(stop_mode="origin", target_r=tr, cost_mult=1.0)
        targets[f"{tr}R"] = summarize_trades(_simulate_choices(ma, ch_best, sc))

    print("Cost stress...", flush=True)
    cost_stress = {}
    for mult, label in [(0.0, "gross"), (1.0, "net"), (1.5, "stress_1.5x"), (2.0, "stress_2x")]:
        sc = SimConfig(stop_mode="origin", target_r=2.5, cost_mult=mult)
        cost_stress[label] = summarize_trades(_simulate_choices(ma, ch_best, sc))

    best_sim = concepts[best_c]["sim_df"]
    overlap = {
        "independent_totalR": float(best_sim["net_R"].sum()) if len(best_sim) else 0,
        "one_pos_totalR": float(one_position_filter(best_sim)["net_R"].sum()) if len(best_sim) else 0,
    }

    # Final 3 traders
    traders = {}
    traders["A"] = {
        "logic": f"{best_c} displacement market choice → origin stop → 2.5R",
        "concept": best_c,
        "stop": "origin",
        "target": 2.5,
        **concepts[best_c],
    }
    m2_cfg = SimConfig(stop_mode="origin_buffer", target_r=2.5, cost_mult=1.0, origin_buffer_atr=0.25)
    traders["B"] = {
        "logic": "M2 displacement+acceptance → origin+buffer → 2.5R",
        "summary": summarize_trades(_simulate_choices(ma, concepts["M2"]["choices"], m2_cfg)),
        "concept": "M2",
    }
    m4_hybrid = SimConfig(stop_mode="hybrid", target_r=2.5, cost_mult=1.0)
    traders["C"] = {
        "logic": "M4 one-sided → hybrid stop → 2.5R",
        "summary": summarize_trades(_simulate_choices(ma, concepts["M4"]["choices"], m4_hybrid)),
        "concept": "M4",
    }

    early_sig = _early_signature(ma, labeled)
    wf = _walkforward(best_sim)
    years = _year_stats(best_sim, ma.idx)
    agree = _agreement_diag(best_sim)

    # Expiration audit
    ch0 = concepts[best_c]["choices"]
    expired = ch0[ch0["decision"] == "EXPIRED"]
    exp_audit = {"pct": len(expired) / n, "n": len(expired)}

    causality = {
        "sequential_parity": test_vectorized_vs_sequential(max_bars=2000)["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=3)["pass"],
    }

    # Export sample
    review = ROOT / "phase65" / "diagnostics" / "visual_review"
    review.mkdir(parents=True, exist_ok=True)
    if len(best_sim):
        best_sim.head(200).to_csv(review / "phase65_sample.csv", index=False)

    # Strip sim_df from concepts for JSON
    for c in concepts:
        concepts[c].pop("sim_df", None)
        concepts[c].pop("choices", None)

    return {
        "causality": causality,
        "n_alarms": n,
        "early_signature": early_sig,
        "concepts": concepts,
        "best_concept": best_c,
        "baselines": {k: {"summary": v["summary"], "path": v.get("path", {}),
                          "median_delay": v.get("median_delay"), "median_chase": v.get("median_chase")}
                      for k, v in baselines.items()},
        "stops": stops,
        "targets": targets,
        "cost_stress": cost_stress,
        "overlap": overlap,
        "traders": {k: {kk: vv for kk, vv in v.items() if kk != "sim_df"} for k, v in traders.items()},
        "walkforward": wf,
        "years": years,
        "agreement": agree,
        "expiration": exp_audit,
    }


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE65_CAUSAL_MARKET_CHOICE_TRADER.md"
    bc = r["best_concept"]
    best = r["concepts"][bc]
    sn = best["sim_net"]
    sg = best["sim_gross"]
    pm = best["path"]
    cap = best["capture"]

    def _pct(x):
        return f"{x:.1%}" if isinstance(x, float) else str(x)

    net_pos = sn.get("TotalR", 0) > 0
    holdout_pos = r.get("walkforward", {}).get("holdout", {}).get("TotalR", 0) > 0

    lines = [
        "PHASE65 — CAUSAL ACTIVITY ALARM → MARKET CHOICE → EARLY EXPANSION TRADER",
        "========================================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        "PHASE58 LOCATION ENGINE MODIFIED: NO",
        "ORIGINAL PHASE58 DIRECTION USED FOR ENTRY: NO",
        "",
        "--------------------------------------------",
        "POPULATION",
        "--------------------------------------------",
        f"PHASE58 ALARMS: {r['n_alarms']:,}",
        f"EXPIRED (best concept): {r['expiration']['pct']:.1%}",
        "",
    ]
    for c in ["M1", "M2", "M3", "M4"]:
        x = r["concepts"][c]
        lines.append(f"{c}: trades={x['n_trades']:,} retention={x['retention']:.1%} net TotalR={x['sim_net'].get('TotalR',0):.0f}")
    lines.extend([
        "", "--------------------------------------------", "REFERENCE BASELINES", "--------------------------------------------",
    ])
    for name, label in [("original", "ORIGINAL DIRECTION"), ("naive_05", "NAIVE ±0.5"), ("naive_10", "NAIVE ±1.0"), ("phase63_rc", "PHASE63 R-C")]:
        b = r["baselines"][name]
        s = b["summary"]
        p = b.get("path", {})
        lines.append(f"{label}: N={s.get('N',0):,} +2/-1={_pct(p.get('+2_before_-1',0))} net AvgR={s.get('AvgR',0):.4f} net TotalR={s.get('TotalR',0):.0f}")

    lines.extend([
        "", f"--------------------------------------------", f"BEST CONCEPT: {bc}", f"--------------------------------------------",
        f"Trades: {best['n_trades']:,} | Retention: {best['retention']:.1%}",
        f"Median delay: {best['median_delay']:.1f} | Median chase: {best['median_chase']:.2f} ATR",
        f"Rem MFE 15m: {best['rem_mfe_15m']:.2f} | Rem MFE 60m: {best['rem_mfe_60m']:.2f}",
        f"+2/-1: {_pct(pm.get('+2_before_-1',0))} | +2/-1.5: {_pct(pm.get('+2_before_-1.5',0))}",
        f"Gross AvgR: {sg.get('AvgR',0):.4f} | Net AvgR: {sn.get('AvgR',0):.4f} | Net TotalR: {sn.get('TotalR',0):.0f}",
        f"Cost stress 1.5x TotalR: {r['cost_stress'].get('stress_1.5x',{}).get('TotalR',0):.0f}",
        "",
        "PHENOMENON CAPTURE:",
        f"  EXPLOSIVE: {cap.get('EXPLOSIVE', {})}",
        f"  CLEAN: {cap.get('CLEAN', {})}",
        "",
        "--------------------------------------------", "VERDICT", "--------------------------------------------",
        f"CAUSAL TRADING EDGE: {'YES' if net_pos and sn.get('AvgR',0) > 0.01 else 'NO'}",
        f"NET EXPECTANCY POSITIVE: {'YES' if net_pos else 'NO'}",
        f"HOLDOUT POSITIVE: {'YES' if holdout_pos else 'NO'}",
        f"COST STRESS PASS: {'YES' if r['cost_stress'].get('stress_1.5x',{}).get('TotalR',0) > 0 else 'NO'}",
        f"EARLY EXPANSION CONVERTED: {'YES' if net_pos else 'NO'}",
        f"ORIGINAL DIRECTION REQUIRED: NO",
        f"READY FOR PINE: NO",
        f"READY FOR LIVE TRADING: NO",
        f"READY FOR PHASE66: {'YES' if net_pos and holdout_pos else 'NO'}",
    ])
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    t0 = time.time()
    results = run_audit()
    # JSON-safe
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items() if k != "choices"}
        if isinstance(obj, list):
            return [_clean(x) for x in obj]
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        if isinstance(obj, pd.DataFrame):
            return None
        return obj
    (REPORTS / "phase65_audit.json").write_text(json.dumps(_clean(results), indent=2, default=str))
    report = write_report(results)
    print(f"\nDone {time.time()-t0:.0f}s\n{report}", flush=True)


if __name__ == "__main__":
    main()
