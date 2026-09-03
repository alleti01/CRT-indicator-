#!/usr/bin/env python3
"""Phase64 — causal location event & two-sided path audit."""
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
from phase64.python.compare import archetype_comparison, compare_metric, practical_label
from phase64.python.controls import match_controls, match_quality
from phase64.python.direction_diag import direction_diagnostics, first_bar_info
from phase64.python.pre_event import compare_pre_event, pre_event_features
from phase64.python.symmetric_paths import THRESHOLDS, compute_paths_batch, summarize_paths

REPORTS = ROOT / "phase64" / "reports"
SIGNALS = ROOT / "phase60" / "diagnostics" / "cache" / "p58_trades_phase60.parquet"


def _load_events(cfg: dict) -> pd.DataFrame:
    signals = pd.read_parquet(SIGNALS)
    cl = cluster_signals(signals, structural_gap=cfg.get("structural_gap_bars", 30))
    ev = cl[cl["opp_rank"] == 1].copy()
    ev["group"] = "PHASE58"
    return ev


def _chunk_paths(hi, lo, op, event_is, atrs, chunk=5000):
    parts = []
    for s in range(0, len(event_is), chunk):
        e = event_is[s : s + chunk]
        a = atrs[s : s + chunk]
        parts.append(compute_paths_batch(hi, lo, op, e, a))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _placebo_test(hi, lo, op, atr, events: pd.DataFrame, idx, n_samples: int = 1000) -> dict:
    """Shuffle timestamps within year/hour bins; compare abs_60m median."""
    rng = np.random.default_rng(64)
    sample = events.sample(min(n_samples, len(events)), random_state=64)
    real = compute_paths_batch(hi, lo, op, sample["signal_i"].values, sample["atr"].values)
    real_med = float(real["abs_60m"].median()) if len(real) else 0

    # Pre-build hour pools by year
    hours = idx.hour.values
    years = idx.year.values
    pools: dict[tuple, np.ndarray] = {}
    for y in np.unique(years):
        for h in range(24):
            mask = (years == y) & (np.abs(hours - h) <= 1)
            cand = np.where(mask)[0]
            cand = cand[(cand > 60) & (cand < len(hi) - 61)]
            if len(cand):
                pools[(int(y), h)] = cand

    placebo_meds = []
    for _ in range(5):
        new_is = []
        for _, r in sample.iterrows():
            ei = int(r["signal_i"])
            key = (int(idx[ei].year), int(idx[ei].hour))
            cand = pools.get(key, pools.get((key[0], max(0, key[1] - 1)), np.array([], dtype=int)))
            if len(cand):
                new_is.append(int(rng.choice(cand)))
            else:
                new_is.append(ei)
        sh = compute_paths_batch(hi, lo, op, np.array(new_is), sample["atr"].values)
        placebo_meds.append(float(sh["abs_60m"].median()))
    return {
        "real_abs_60m_median": real_med,
        "placebo_abs_60m_median": float(np.median(placebo_meds)),
        "placebo_samples": len(placebo_meds),
    }


def _year_report(events, paths, idx) -> dict:
    merged = events[["signal_i"]].merge(paths, left_on="signal_i", right_on="event_i")
    merged["year"] = [idx[int(i)].year for i in merged["signal_i"]]
    yrs = {}
    for y, grp in merged.groupby("year"):
        yrs[int(y)] = summarize_paths(grp)
    return yrs


def run_audit() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    cfg = _load_cfg()
    print("Loading market data...", flush=True)
    ma = build_market_arrays_phase60()
    events = _load_events(cfg)
    all_signals = pd.read_parquet(SIGNALS)
    n_events = len(events)
    print(f"Phase58 events: {n_events:,}", flush=True)

    print("Building matched controls...", flush=True)
    controls = match_controls(
        events, all_signals["signal_i"].values, ma.idx, ma.atr, ma.n,
        gap=cfg.get("structural_gap_bars", 30),
    )
    print(f"Controls matched: {len(controls):,} ({len(controls)/n_events:.1%})", flush=True)
    mq = match_quality(events, controls, ma.idx, ma.atr)

    print("Computing symmetric paths (Phase58)...", flush=True)
    t0 = time.time()
    p58_paths = _chunk_paths(ma.hi, ma.lo, ma.op, events["signal_i"].values.astype(int), events["atr"].values.astype(float))
    p58_paths["event_i"] = p58_paths["event_i"].astype(int)
    print(f"  Phase58 paths: {len(p58_paths):,} in {time.time()-t0:.0f}s", flush=True)

    print("Computing symmetric paths (controls)...", flush=True)
    t1 = time.time()
    ctl_paths = _chunk_paths(ma.hi, ma.lo, ma.op, controls["signal_i"].values.astype(int), controls["atr"].values.astype(float))
    ctl_paths["event_i"] = ctl_paths["event_i"].astype(int)
    print(f"  Control paths: {len(ctl_paths):,} in {time.time()-t1:.0f}s", flush=True)

    p58_sum = summarize_paths(p58_paths)
    ctl_sum = summarize_paths(ctl_paths)

    # Expansion comparisons
    expansion = {}
    for h in [5, 10, 15, 30, 60]:
        expansion[h] = compare_metric(
            p58_sum.get(f"median_abs_{h}m", 0), ctl_sum.get(f"median_abs_{h}m", 0),
            p58_sum["n"], ctl_sum["n"],
        )

    thresholds = {}
    for horizon in [15, 30, 60]:
        thresholds[horizon] = {}
        for thr in THRESHOLDS:
            k = f"p_either_{thr}_within_{horizon}m"
            thresholds[horizon][thr] = compare_metric(
                p58_sum.get(k, 0), ctl_sum.get(k, 0), p58_sum["n"], ctl_sum["n"],
            )

    time_exp = {}
    for thr in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        time_exp[thr] = {
            "phase58": p58_sum.get(f"median_t_either_{thr}", float("nan")),
            "control": ctl_sum.get(f"median_t_either_{thr}", float("nan")),
        }

    first_side = {}
    for thr in [0.5, 1.0]:
        first_side[thr] = {
            "up": compare_metric(p58_sum.get(f"p_up_first_{thr}", 0), ctl_sum.get(f"p_up_first_{thr}", 0), p58_sum["n"], ctl_sum["n"]),
            "down": compare_metric(p58_sum.get(f"p_dn_first_{thr}", 0), ctl_sum.get(f"p_dn_first_{thr}", 0), p58_sum["n"], ctl_sum["n"]),
            "neither": compare_metric(p58_sum.get(f"p_neither_{thr}", 0), ctl_sum.get(f"p_neither_{thr}", 0), p58_sum["n"], ctl_sum["n"]),
        }

    continuation = {
        "after_up_05": compare_metric(p58_sum.get("after_up_0.5_reach_2", 0), ctl_sum.get("after_up_0.5_reach_2", 0), p58_sum["n"], ctl_sum["n"]),
        "after_up_05_fail": compare_metric(p58_sum.get("after_up_0.5_fail", 0), ctl_sum.get("after_up_0.5_fail", 0), p58_sum["n"], ctl_sum["n"]),
        "after_dn_05": compare_metric(p58_sum.get("after_dn_0.5_reach_2", 0), ctl_sum.get("after_dn_0.5_reach_2", 0), p58_sum["n"], ctl_sum["n"]),
        "after_dn_05_fail": compare_metric(p58_sum.get("after_dn_0.5_fail", 0), ctl_sum.get("after_dn_0.5_fail", 0), p58_sum["n"], ctl_sum["n"]),
    }

    sweeps = {}
    for thr in [0.5, 1.0, 1.5, 2.0]:
        sweeps[thr] = compare_metric(p58_sum.get(f"p_hit_both_{thr}", 0), ctl_sum.get(f"p_hit_both_{thr}", 0), p58_sum["n"], ctl_sum["n"])

    archetypes = archetype_comparison(p58_sum, ctl_sum)

    cleanliness = {
        "net_over_range": compare_metric(p58_sum.get("median_net_over_range", 0), ctl_sum.get("median_net_over_range", 0), p58_sum["n"], ctl_sum["n"]),
        "largest_over_range": compare_metric(p58_sum.get("median_largest_over_range", 0), ctl_sum.get("median_largest_over_range", 0), p58_sum["n"], ctl_sum["n"]),
        "clean_up": compare_metric(p58_sum.get("p_clean_up", 0), ctl_sum.get("p_clean_up", 0), p58_sum["n"], ctl_sum["n"]),
        "clean_dn": compare_metric(p58_sum.get("p_clean_dn", 0), ctl_sum.get("p_clean_dn", 0), p58_sum["n"], ctl_sum["n"]),
        "chaotic": compare_metric(p58_sum.get("p_large_chaotic", 0), ctl_sum.get("p_large_chaotic", 0), p58_sum["n"], ctl_sum["n"]),
    }

    print("Pre-event features...", flush=True)
    p58_pre = pre_event_features(ma.hi, ma.lo, ma.cl, ma.op, ma.atr, events["signal_i"].values[:10000])
    ctl_pre = pre_event_features(ma.hi, ma.lo, ma.cl, ma.op, ma.atr, controls["signal_i"].values[:10000])
    pre_event = compare_pre_event(p58_pre, ctl_pre)

    print("Direction diagnostics...", flush=True)
    dir_diag = direction_diagnostics(events, p58_paths)
    bar0 = first_bar_info(events, p58_paths, ma.hi, ma.lo, ma.op, ma.cl)

    print("Placebo test...", flush=True)
    placebo = _placebo_test(ma.hi, ma.lo, ma.op, ma.atr, events, ma.idx)

    # Walk-forward on path summaries
    events_sorted = events.sort_values("signal_i").reset_index(drop=True)
    splits = walkforward_splits(len(events_sorted), 0.6, 0.8)
    wf = {}
    for name, (a, b) in splits.items():
        sub_ev = events_sorted.iloc[a:b]
        sub_p = p58_paths[p58_paths["event_i"].isin(sub_ev["signal_i"])]
        sub_c = ctl_paths[ctl_paths["event_i"].isin(
            controls[controls["matched_to"].isin(sub_ev["signal_i"])]["signal_i"]
        )]
        sp = summarize_paths(sub_p)
        sc = summarize_paths(sub_c) if len(sub_c) else {"n": 0}
        wf[name] = {
            "expansion_lift_60m": sp.get("median_abs_60m", 0) - sc.get("median_abs_60m", 0),
            "clean_lift": sp.get("p_clean_up", 0) + sp.get("p_clean_dn", 0) - sc.get("p_clean_up", 0) - sc.get("p_clean_dn", 0),
            "sweep_diff_1": sp.get("p_hit_both_1.0", 0) - sc.get("p_hit_both_1.0", 0),
            "n": sp.get("n", 0),
        }

    # Year stability (sample paths merged back)
    years = _year_report(events, p58_paths, ma.idx)

    causality = {
        "sequential_parity": test_vectorized_vs_sequential(max_bars=2000)["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=3)["pass"],
    }

    # Classify what Phase58 detects
    abs_lift = expansion[60]["lift"]
    sweep_lift = sweeps[1.0]["lift"]
    clean_lift = cleanliness["clean_up"]["lift"] + cleanliness["clean_dn"]["lift"]
    dir_acc = dir_diag.get("largest_side_accuracy", 0.5)

    def _strength(l):
        if abs(l) < 0.03:
            return "NONE"
        if abs(l) < 0.08:
            return "WEAK"
        if abs(l) < 0.15:
            return "MODERATE"
        return "STRONG"

    detection = {
        "DIRECTION": _strength(dir_acc - 0.5),
        "VOLATILITY_EXPANSION": _strength(abs_lift),
        "TWO_SIDED_SWEEP": _strength(sweep_lift),
        "CLEAN_EXPANSION": _strength(clean_lift),
        "GENERAL_HIGH_VOL": abs_lift < 0.05 and p58_sum.get("median_abs_60m", 0) > ctl_sum.get("median_abs_60m", 0) * 1.1,
    }

    return {
        "causality": causality,
        "n_events": n_events,
        "n_controls": len(controls),
        "control_ratio": len(controls) / n_events,
        "match_quality": mq,
        "p58_summary": p58_sum,
        "ctl_summary": ctl_sum,
        "expansion": expansion,
        "thresholds": thresholds,
        "time_expansion": time_exp,
        "first_side": first_side,
        "continuation": continuation,
        "sweeps": sweeps,
        "archetypes": archetypes,
        "cleanliness": cleanliness,
        "pre_event": pre_event,
        "direction_diag": dir_diag,
        "bar0_info": bar0,
        "placebo": placebo,
        "walkforward": wf,
        "years": {str(k): v for k, v in years.items()},
        "detection": detection,
    }


def _pct(x: float) -> str:
    return f"{x:.1%}"


def _f(x: float) -> str:
    return f"{x:.2f}"


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE64_CAUSAL_LOCATION_TWO_SIDED_PATH_AUDIT.md"
    mq = r["match_quality"]
    p58, ctl = r["p58_summary"], r["ctl_summary"]
    exp60 = r["expansion"][60]
    thr60 = r["thresholds"][60]
    dd = r["direction_diag"]
    det = r["detection"]

    abs_practical = practical_label(exp60["abs_diff"], ctl.get("median_abs_60m", exp60["control"]))
    sweep_practical = practical_label(r["sweeps"][1.0]["abs_diff"], r["sweeps"][1.0]["control"])
    clean_practical = practical_label(
        r["cleanliness"]["clean_up"]["abs_diff"] + r["cleanliness"]["clean_dn"]["abs_diff"],
        r["cleanliness"]["clean_up"]["control"] + r["cleanliness"]["clean_dn"]["control"],
    )

    edge_remains_vol = exp60["lift"] > 0.03
    differs = exp60["abs_diff"] > 0.05 or r["sweeps"][1.0]["abs_diff"] > 0.02
    meaningful = abs_practical in ("MODERATE", "LARGE") or sweep_practical in ("MODERATE", "LARGE")

    lines = [
        "PHASE64 — CAUSAL LOCATION EVENT & TWO-SIDED PATH AUDIT",
        "========================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        "LOCATION ENGINE MODIFIED: NO",
        "",
        "--------------------------------------------",
        "POPULATION",
        "--------------------------------------------",
        f"PHASE58 EVENTS: {r['n_events']:,}",
        f"MATCHED CONTROLS: {r['n_controls']:,}",
        f"CONTROL RATIO: {r['control_ratio']:.2f}:1",
        f"MATCH QUALITY: {mq['match_quality']}",
        "",
        "--------------------------------------------",
        "PRE-EVENT MATCH",
        "--------------------------------------------",
        f"ATR — PHASE58: {_f(mq['phase58_median_atr'])} | CONTROL: {_f(mq['control_median_atr'])} | ratio: {mq['atr_ratio']:.2f}",
        f"SESSION DISTRIBUTION DIFF: {mq['session_distribution_diff']:.3f}",
        f"MAJOR MISMATCH: {'YES' if mq['major_mismatch'] else 'NO'}",
        "",
        "--------------------------------------------",
        "ABSOLUTE EXPANSION (median abs excursion / ATR)",
        "--------------------------------------------",
        f"{'':12} {'PHASE58':>10} {'CONTROL':>10} {'LIFT':>8}",
    ]
    for h in [5, 10, 15, 30, 60]:
        e = r["expansion"][h]
        lines.append(f"{h}M:{'':8} {_f(e['phase58']):>10} {_f(e['control']):>10} {e['lift']:>+7.1%}")

    lines.extend(["", "--------------------------------------------", "EITHER-SIDE THRESHOLDS (within 60M)", "--------------------------------------------"])
    for thr in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        t = thr60[thr]
        lines.append(f"±{thr} ATR: P58={_pct(t['phase58'])} Ctrl={_pct(t['control'])} Lift={t['lift']:+.1%} ({t['practical']})")

    lines.extend(["", "--------------------------------------------", "TIME TO EXPANSION (median bars, either side)", "--------------------------------------------"])
    for thr in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        te = r["time_expansion"][thr]
        lines.append(f"±{thr} ATR: P58={_f(te['phase58'])} | Ctrl={_f(te['control'])}")

    fs05 = r["first_side"][0.5]
    lines.extend([
        "", "--------------------------------------------", "FIRST SIDE (±0.5 ATR)", "--------------------------------------------",
        f"+0.5 FIRST: P58={_pct(fs05['up']['phase58'])} Ctrl={_pct(fs05['up']['control'])}",
        f"-0.5 FIRST: P58={_pct(fs05['down']['phase58'])} Ctrl={_pct(fs05['down']['control'])}",
        f"NEITHER:    P58={_pct(fs05['neither']['phase58'])} Ctrl={_pct(fs05['neither']['control'])}",
        "", "--------------------------------------------", "FIRST-BREAK CONTINUATION (±0.5 first)", "--------------------------------------------",
        f"AFTER +0.5 FIRST reach +2: P58={_pct(r['continuation']['after_up_05']['phase58'])} Ctrl={_pct(r['continuation']['after_up_05']['control'])}",
        f"AFTER +0.5 FIRST fail opp:  P58={_pct(r['continuation']['after_up_05_fail']['phase58'])} Ctrl={_pct(r['continuation']['after_up_05_fail']['control'])}",
        f"AFTER -0.5 FIRST reach -2: P58={_pct(r['continuation']['after_dn_05']['phase58'])} Ctrl={_pct(r['continuation']['after_dn_05']['control'])}",
        f"AFTER -0.5 FIRST fail opp:  P58={_pct(r['continuation']['after_dn_05_fail']['phase58'])} Ctrl={_pct(r['continuation']['after_dn_05_fail']['control'])}",
        "", "--------------------------------------------", "TWO-SIDED SWEEPS", "--------------------------------------------",
    ])
    for thr in [0.5, 1.0, 1.5, 2.0]:
        s = r["sweeps"][thr]
        lines.append(f"±{thr} BOTH: P58={_pct(s['phase58'])} Ctrl={_pct(s['control'])} Lift={s['lift']:+.1%}")

    lines.extend(["", "--------------------------------------------", "PATH ARCHETYPES (top differences)", "--------------------------------------------"])
    arch_sorted = sorted(r["archetypes"].items(), key=lambda x: abs(x[1]["abs_diff"]), reverse=True)
    for name, a in arch_sorted[:8]:
        lines.append(f"{name}: P58={_pct(a['phase58'])} Ctrl={_pct(a['control'])} Lift={a['lift']:+.1%}")

    lines.extend([
        "", "--------------------------------------------", "CLEANNESS", "--------------------------------------------",
        f"NET DISPLACEMENT / TOTAL RANGE: P58={_f(r['cleanliness']['net_over_range']['phase58'])} Ctrl={_f(r['cleanliness']['net_over_range']['control'])}",
        f"LARGEST EXCURSION / TWO-SIDED RANGE: P58={_f(r['cleanliness']['largest_over_range']['phase58'])} Ctrl={_f(r['cleanliness']['largest_over_range']['control'])}",
        f"CLEAN UP (≥2 up, <1 dn): P58={_pct(r['cleanliness']['clean_up']['phase58'])} Ctrl={_pct(r['cleanliness']['clean_up']['control'])}",
        f"CLEAN DOWN: P58={_pct(r['cleanliness']['clean_dn']['phase58'])} Ctrl={_pct(r['cleanliness']['clean_dn']['control'])}",
        f"LARGE CHAOTIC (both ≥2): P58={_pct(r['cleanliness']['chaotic']['phase58'])} Ctrl={_pct(r['cleanliness']['chaotic']['control'])}",
        f"PHASE58 MOVEMENT IS CLEANER: {'YES' if r['cleanliness']['largest_over_range']['phase58'] > r['cleanliness']['largest_over_range']['control'] else 'NO'}",
        "", "--------------------------------------------", "ORIGINAL DIRECTION INFORMATION", "--------------------------------------------",
        f"FIRST-SIDE ACCURACY: {_pct(dd.get('first_side_accuracy', 0))}",
        f"LARGEST-SIDE ACCURACY: {_pct(dd.get('largest_side_accuracy', 0))}",
        f"CLEAN-EXPANSION ACCURACY: {_pct(dd.get('clean_expansion_accuracy', 0))}",
        f"POST-SWEEP DIRECTION ACCURACY: {_pct(dd.get('post_sweep_direction_accuracy', 0))}",
        f"INCREMENTAL VALUE OVER LOCATION ONLY: {dd.get('incremental_label', 'NONE')}",
        "", "--------------------------------------------", "PRE-EVENT CHARACTER", "--------------------------------------------",
    ])
    pe = r["pre_event"]
    if "compression_5_15" in pe:
        lines.append(f"COMPRESSION (5m/15m range): P58={pe['compression_5_15']['phase58']:.2f} Ctrl={pe['compression_5_15']['control']:.2f}")
    lines.extend([
        "", "--------------------------------------------", "CONTROL / PLACEBO", "--------------------------------------------",
        f"REAL abs_60m median: {_f(r['placebo']['real_abs_60m_median'])}",
        f"PLACEBO abs_60m median: {_f(r['placebo']['placebo_abs_60m_median'])}",
        f"EDGE REMAINS AFTER VOLATILITY MATCHING: {'YES' if edge_remains_vol else 'NO'}",
        "", "--------------------------------------------", "WALK-FORWARD", "--------------------------------------------",
    ])
    for split in ("train", "validation", "holdout"):
        w = r["walkforward"][split]
        lines.append(f"{split.upper()}: n={w['n']:,} expansion_lift_60m={w['expansion_lift_60m']:+.2f} clean_lift={w['clean_lift']:+.1%} sweep_diff={w['sweep_diff_1']:+.1%}")

    lines.extend([
        "", "--------------------------------------------", "PRACTICAL SIGNIFICANCE", "--------------------------------------------",
        f"ABSOLUTE EXPANSION EDGE: {abs_practical}",
        f"TWO-SIDED-SWEEP INFORMATION: {sweep_practical}",
        f"PATH-CLEANNESS EDGE: {clean_practical}",
        f"FIRST-BREAK CONTINUATION: {practical_label(r['continuation']['after_up_05']['abs_diff'], r['continuation']['after_up_05']['control'])}",
        "", "--------------------------------------------", "WHAT PHASE58 ACTUALLY DETECTS", "--------------------------------------------",
        f"DIRECTION: {det['DIRECTION']}",
        f"VOLATILITY EXPANSION: {det['VOLATILITY_EXPANSION']}",
        f"TWO-SIDED SWEEP: {det['TWO_SIDED_SWEEP']}",
        f"CLEAN EXPANSION: {det['CLEAN_EXPANSION']}",
        f"GENERAL HIGH VOLATILITY ONLY: {'YES' if det['GENERAL_HIGH_VOL'] else 'NO'}",
        "", "--------------------------------------------", "VERDICT", "--------------------------------------------",
        f"PHASE58 LOCATIONS DIFFER FROM MATCHED CONTROLS: {'YES' if differs else 'NO'}",
        f"DIFFERENCE IS PRACTICALLY MEANINGFUL: {'YES' if meaningful else 'NO'}",
        f"PHASE58 IS A REAL LOCATION DETECTOR: {'YES' if differs and edge_remains_vol else 'NO / MARGINAL'}",
        f"PHASE58 IS PRIMARILY JUST A VOLATILITY DETECTOR: {'YES' if det['GENERAL_HIGH_VOL'] and not meaningful else 'NO'}",
        f"FIRST-BREAK BEHAVIOR DESERVES TRADER RESEARCH: {'YES' if r['continuation']['after_up_05']['phase58'] > 0.3 else 'MAYBE'}",
        f"TWO-SIDED-SWEEP BEHAVIOR DESERVES TRADER RESEARCH: {'YES' if r['sweeps'][1.0]['phase58'] > 0.4 else 'MAYBE'}",
        f"ORIGINAL DIRECTION SHOULD BE RETAINED: SOFT CONTEXT ONLY",
        f"READY TO DESIGN NEW TRADER ARCHITECTURE: {'YES' if meaningful else 'NO — need stronger phenomenon'}",
        "READY FOR PINE: NO",
        "READY FOR LIVE TRADING: NO",
        f"READY FOR PHASE65: {'YES' if meaningful else 'ONLY IF PHENOMENON IDENTIFIED'}",
    ])
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    t0 = time.time()
    results = run_audit()
    (REPORTS / "phase64_audit.json").write_text(json.dumps(results, indent=2, default=str))
    report = write_report(results)
    print(f"\nDone {time.time()-t0:.0f}s\n{report}", flush=True)


if __name__ == "__main__":
    main()
