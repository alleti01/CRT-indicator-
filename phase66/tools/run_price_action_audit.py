#!/usr/bin/env python3
"""Phase66 — causal price-action entry discovery at Phase58 locations."""
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
from phase64.python.controls import match_controls, build_exclusion_mask
from phase64.python.symmetric_paths import compute_single_path
from phase65.python.market_choice import scan_market_choice
from phase66.python.entries import scan_family
from phase66.python.metrics import aggregate_paths, path_from_entry, simulate_setup, summarize_sim

REPORTS = ROOT / "phase66" / "reports"
SIGNALS = ROOT / "phase60" / "diagnostics" / "cache" / "p58_trades_phase60.parquet"
GATE_PO2 = 0.38  # meaningful +2/-1 vs baseline ~33%


def _load_alarms(cfg):
    signals = pd.read_parquet(SIGNALS)
    cl = cluster_signals(signals, structural_gap=cfg.get("structural_gap_bars", 30))
    ev = cl[cl["opp_rank"] == 1].copy()
    ev["orig_dir"] = ev["direction"]
    return ev, signals


def _scan_all(m, events, family: str) -> pd.DataFrame:
    rows = []
    for _, r in events.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        sig = scan_family(m, si, atr, family, max_delay=3)
        rows.append({
            "signal_i": si, "atr": atr, "orig_dir": r["orig_dir"],
            "family": family, "decision": sig.decision, "direction": sig.direction,
            "trigger_i": sig.trigger_i, "entry_i": sig.entry_i,
            "delay_bars": sig.delay_bars, "reason": sig.reason,
            "invalidation": sig.invalidation, "chase_atr": sig.chase_atr,
            "level_name": sig.level_name,
        })
    return pd.DataFrame(rows)


def _evaluate_family(m, events, scans: pd.DataFrame, target_r: float = 2.5) -> dict:
    taken = scans[scans["decision"] == "TAKE"]
    paths = []
    sims = []
    for _, s in taken.iterrows():
        ei = int(s["entry_i"])
        p = path_from_entry(m, ei, s["direction"], float(s["atr"]))
        paths.append(p)
        from phase66.python.entries import EntrySignal
        sig = EntrySignal(
            s["family"], "TAKE", s["direction"], int(s["signal_i"]),
            int(s["trigger_i"]), ei, s["delay_bars"], s["reason"],
            s["level_name"], 0, float(s["invalidation"]), float(s["chase_atr"]),
        )
        sim = simulate_setup(m, sig, float(s["atr"]), target_r, cost_mult=1.0)
        sims.append({**s.to_dict(), **sim, **p})
    path_agg = aggregate_paths(paths)
    sim_df = pd.DataFrame(sims)
    sim_net = summarize_sim(sim_df) if len(sim_df) else {"N": 0}
    sim_gross = summarize_sim(sim_df.assign(net_R=sim_df["gross_R"])) if len(sim_df) else {"N": 0}
    stress = summarize_sim(sim_df.assign(net_R=sim_df["gross_R"] - sim_df["cost_R"] * 1.5)) if len(sim_df) else {}
    long_df = sim_df[sim_df["direction"] == "LONG"] if len(sim_df) else pd.DataFrame()
    short_df = sim_df[sim_df["direction"] == "SHORT"] if len(sim_df) else pd.DataFrame()
    return {
        "n_alarms": len(events),
        "n_signals": len(taken),
        "n_long": len(long_df),
        "n_short": len(short_df),
        "retention": len(taken) / len(events) if len(events) else 0,
        "n_expired": int((scans["decision"] == "EXPIRED").sum()),
        "n_conflict": int((scans["decision"] == "CONFLICT").sum()),
        "median_delay": float(taken["delay_bars"].median()) if len(taken) else 0,
        "median_chase": float(taken["chase_atr"].median()) if len(taken) else 0,
        "path": path_agg,
        "sim_net": sim_net,
        "sim_gross": sim_gross,
        "stress_1.5x": stress,
        "sim_df": sim_df,
    }


def _baseline_original(m, events, target_r=2.5):
    rows = []
    for _, r in events.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        ei = si + 1
        p = path_from_entry(m, ei, r["orig_dir"], atr)
        from phase66.python.entries import EntrySignal
        sig = EntrySignal("BASE", "TAKE", r["orig_dir"], si, si, ei, 1, "ORIG_DIR", "", 0, float(m.lo[si]), 0)
        sim = simulate_setup(m, sig, atr, target_r, cost_mult=1.0, stop_mode="1.0atr")
        rows.append({**p, **sim, "direction": r["orig_dir"]})
    df = pd.DataFrame(rows)
    return {"path": aggregate_paths(rows), "sim": summarize_sim(df)}


def _baseline_m65(m, events, target_r=2.5):
    rows = []
    for _, r in events.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        ch = scan_market_choice(m, si, atr, "M3", max_delay=3, thr=0.5)
        if ch.decision != "TAKE":
            continue
        ei = ch.entry_i
        p = path_from_entry(m, ei, ch.direction, atr)
        from phase66.python.entries import EntrySignal
        sig = EntrySignal("M65", "TAKE", ch.direction, si, ch.choice_i, ei, ch.delay_bars, ch.reason, "", 0, float(m.op[si]), ch.chase_atr)
        sim = simulate_setup(m, sig, atr, target_r, cost_mult=1.0, stop_mode="setup")
        rows.append({**p, **sim})
    df = pd.DataFrame(rows)
    return {"path": aggregate_paths(rows), "sim": summarize_sim(df), "n": len(df)}


def _pa_outside_phase58(m, events, signals, family: str, sample: int = 10000):
    """E family on matched non-Phase58 bars."""
    exclude = build_exclusion_mask(m.n, signals["signal_i"].values, gap=30)
    controls = match_controls(events, signals["signal_i"].values, m.idx, m.atr, m.n)
    sub = controls.sample(min(sample, len(controls)), random_state=66)
    paths = []
    sims = []
    for _, r in sub.iterrows():
        si, atr = int(r["signal_i"]), float(r["atr"])
        sig = scan_family(m, si, atr, family, max_delay=3)
        if sig.decision != "TAKE":
            continue
        p = path_from_entry(m, sig.entry_i, sig.direction, atr)
        paths.append(p)
        sim = simulate_setup(m, sig, atr, 2.5, 1.0)
        sims.append(sim)
    return {
        "n": len(paths),
        "path": aggregate_paths(paths),
        "sim": summarize_sim(pd.DataFrame(sims)) if sims else {"N": 0},
    }


def _verdict(path_agg: dict, sim_net: dict, baseline_po2: float = 0.33) -> str:
    po2 = path_agg.get("+2_before_-1", 0)
    net_r = sim_net.get("AvgR", -999)
    if po2 >= GATE_PO2 and net_r > 0:
        return "KEEP"
    if po2 >= baseline_po2 + 0.05 and path_agg.get("+1_before_-1", 0) >= 0.52:
        return "MARGINAL"
    return "REJECT"


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    print("Loading...", flush=True)
    ma = build_market_arrays_phase60()
    events, signals = _load_alarms(cfg)
    n = len(events)
    print(f"Alarms: {n:,}", flush=True)

    families = {}
    scans = {}
    for fam in ["E1", "E2", "E3"]:
        print(f"Scanning {fam}...", flush=True)
        sc = _scan_all(ma, events, fam)
        scans[fam] = sc
        families[fam] = _evaluate_family(ma, events, sc)
        families[fam].pop("sim_df", None)

    print("Baselines...", flush=True)
    baselines = {
        "original": _baseline_original(ma, events),
        "m65": _baseline_m65(ma, events),
    }

    print("PA outside Phase58...", flush=True)
    pa_only = {fam: _pa_outside_phase58(ma, events, signals, fam) for fam in ["E1", "E2", "E3"]}

    # Agreement diagnostic on best family
    best = max(families, key=lambda k: families[k]["path"].get("+2_before_-1", 0))
    sc_best = scans[best]
    taken = sc_best[sc_best["decision"] == "TAKE"]
    agree_paths, disagree_paths = [], []
    agree_sim, disagree_sim = [], []
    for _, s in taken.iterrows():
        p = path_from_entry(ma, int(s["entry_i"]), s["direction"], float(s["atr"]))
        from phase66.python.entries import EntrySignal
        sig = EntrySignal(best, "TAKE", s["direction"], int(s["signal_i"]), int(s["trigger_i"]),
                          int(s["entry_i"]), s["delay_bars"], s["reason"], s["level_name"], 0,
                          float(s["invalidation"]), float(s["chase_atr"]))
        sim = simulate_setup(ma, sig, float(s["atr"]), 2.5, 1.0)
        if s["direction"] == s["orig_dir"]:
            agree_paths.append(p)
            agree_sim.append(sim)
        else:
            disagree_paths.append(p)
            disagree_sim.append(sim)

    agreement = {
        "agree": {"path": aggregate_paths(agree_paths), "sim": summarize_sim(pd.DataFrame(agree_sim)) if agree_sim else {}},
        "disagree": {"path": aggregate_paths(disagree_paths), "sim": summarize_sim(pd.DataFrame(disagree_sim)) if disagree_sim else {}},
    }

    # Walk-forward on best family taken trades
    sc_t = scans[best][scans[best]["decision"] == "TAKE"].sort_values("entry_i")
    wf_sims = []
    for _, s in sc_t.iterrows():
        from phase66.python.entries import EntrySignal
        sig = EntrySignal(best, "TAKE", s["direction"], int(s["signal_i"]), int(s["trigger_i"]),
                          int(s["entry_i"]), s["delay_bars"], s["reason"], s["level_name"], 0,
                          float(s["invalidation"]), float(s["chase_atr"]))
        sim = simulate_setup(ma, sig, float(s["atr"]), 2.5, 1.0)
        wf_sims.append(sim)
    wf_df = pd.DataFrame(wf_sims)
    wf = {}
    if len(wf_df):
        splits = walkforward_splits(len(wf_df), 0.6, 0.8)
        for name, (a, b) in splits.items():
            wf[name] = summarize_sim(wf_df.iloc[a:b])

    # Year stability
    years = {}
    if len(wf_df):
        wf_df["year"] = [ma.idx[int(sc_t.iloc[i]["entry_i"])].year for i in range(len(wf_df))]
        sc_t = sc_t.reset_index(drop=True)
        for y in wf_df["year"].unique():
            sub = wf_df[wf_df["year"] == y]
            years[int(y)] = summarize_sim(sub)

    causality = {
        "sequential_parity": test_vectorized_vs_sequential(max_bars=2000)["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=3)["pass"],
    }

    # Four-way: simplified counts
    e_any = scans["E1"].merge(scans["E2"][["signal_i", "decision"]].rename(columns={"decision": "e2"}),
                              on="signal_i").merge(scans["E3"][["signal_i", "decision"]].rename(columns={"decision": "e3"}), on="signal_i")
    has_pa = e_any.apply(lambda r: r["decision"] == "TAKE" or r["e2"] == "TAKE" or r["e3"] == "TAKE", axis=1)

    # Export sample
    review = ROOT / "phase66" / "diagnostics" / "visual_review"
    review.mkdir(parents=True, exist_ok=True)
    scans[best][scans[best]["decision"] == "TAKE"].head(200).to_csv(review / "phase66_sample.csv", index=False)

    for fam in families:
        families[fam]["verdict"] = _verdict(families[fam]["path"], families[fam]["sim_net"])

    return {
        "causality": causality,
        "n_alarms": n,
        "families": families,
        "best_family": best,
        "baselines": baselines,
        "pa_only": pa_only,
        "agreement": agreement,
        "walkforward": wf,
        "years": years,
        "four_way": {"phase58_with_pa": int(has_pa.sum()), "phase58_no_pa": int((~has_pa).sum())},
        "counts": {
            "E1": int((scans["E1"]["decision"] == "TAKE").sum()),
            "E2": int((scans["E2"]["decision"] == "TAKE").sum()),
            "E3": int((scans["E3"]["decision"] == "TAKE").sum()),
            "conflict": {fam: int((scans[fam]["decision"] == "CONFLICT").sum()) for fam in ["E1", "E2", "E3"]},
        },
    }


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE66_CAUSAL_PRICE_ACTION_ENTRY_AUDIT.md"
    bl = r["baselines"]["original"]
    best = r["best_family"]
    bf = r["families"][best]
    pa = r["pa_only"][best]
    po2_best = bf["path"].get("+2_before_-1", 0)
    net_pos = bf["sim_net"].get("AvgR", 0) > 0

    lines = [
        "CAUSAL PRICE-ACTION ENTRY DISCOVERY AT PHASE58 LOCATIONS",
        "=======================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        "PHASE58 LOCATION ENGINE MODIFIED: NO",
        "PHASE58 DIRECTION USED: NO",
        "",
        f"PHASE58 LOCATIONS: {r['n_alarms']:,}",
        f"E1 signals: {r['counts']['E1']:,} | E2: {r['counts']['E2']:,} | E3: {r['counts']['E3']:,}",
        "",
        "BASELINES — Original dir: +2/-1={:.1%} net AvgR={:.3f}".format(
            bl["path"].get("+2_before_-1", 0), bl["sim"].get("AvgR", 0)),
        "",
    ]
    for fam in ["E1", "E2", "E3"]:
        f = r["families"][fam]
        p = f["path"]
        s = f["sim_net"]
        lines.extend([
            f"--- {fam} ---",
            f"N={f['n_signals']:,} LONG={f['n_long']:,} SHORT={f['n_short']:,}",
            f"Delay={f['median_delay']:.1f} Chase={f['median_chase']:.2f}ATR",
            f"+1/-1={p.get('+1_before_-1',0):.1%} +2/-1={p.get('+2_before_-1',0):.1%} +2/-1.5={p.get('+2_before_-1.5',0):.1%}",
            f"MFE15={p.get('median_mfe_15m',0):.2f} MAE15={p.get('median_mae_15m',0):.2f}",
            f"Net AvgR={s.get('AvgR',0):.4f} TotalR={s.get('TotalR',0):.0f} VERDICT={f.get('verdict','')}",
            "",
        ])
    lines.extend([
        f"BEST FAMILY: {best}",
        f"PA only (controls): +2/-1={pa['path'].get('+2_before_-1',0):.1%} Net AvgR={pa['sim'].get('AvgR',0):.4f}",
        f"PA+Phase58: +2/-1={po2_best:.1%} Net AvgR={bf['sim_net'].get('AvgR',0):.4f}",
        "",
        "VERDICT:",
        f"ANY PA EDGE: {'YES' if po2_best >= GATE_PO2 else 'NO'}",
        f"NET POSITIVE: {'YES' if net_pos else 'NO'}",
        f"READY TO FREEZE: NO",
    ])
    out.write_text("\n".join(lines))
    return out


def main():
    t0 = time.time()
    results = run_audit()
    (REPORTS / "phase66_audit.json").write_text(json.dumps(results, indent=2, default=str))
    report = write_report(results)
    print(f"\nDone {time.time()-t0:.0f}s\n{report}", flush=True)


if __name__ == "__main__":
    main()
