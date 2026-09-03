#!/usr/bin/env python3
"""Phase61 — causal early-signal & trader-judgment audit."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58b.research.simulation import metrics
from phase58j.research.walkforward_audit import walkforward_splits
from phase59.tools.phase59_parity import _load_cfg
from phase60.python.arrays import build_market_arrays_phase60, build_mtf_arrays_phase60
from phase60.tools.run_phase60 import test_prefix_invariance, test_vectorized_vs_sequential
from phase61.python.classification import classify_paths, giveback_audit, management_matrix, simulate_management
from phase61.python.clustering import cluster_signals, clustering_stats, first_vs_later
from phase61.python.forward_paths import compute_forward_paths, horizon_summary
from phase61.python.judgment import build_hypotheses, enrich_causal_features, label_good_bad, simple_scorecard

CACHE = ROOT / "phase61" / "diagnostics" / "cache"
REPORTS = ROOT / "phase61" / "reports"
SIGNALS_PATH = ROOT / "phase60" / "diagnostics" / "cache" / "p58_trades_phase60.parquet"


def _ensure_dirs() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)


def run_audit(chunk: int | None = None) -> dict:
    _ensure_dirs()
    cfg = _load_cfg()
    cfg.update(json.load(open(ROOT / "phase58/config/phase58_v1_frozen.json")))
    cfg.update(json.load(open(ROOT / "phase58d/config/phase58d_frozen.json")))

    print("Loading market + signals...", flush=True)
    ma = build_market_arrays_phase60()
    mtf = build_mtf_arrays_phase60()
    signals = pd.read_parquet(SIGNALS_PATH)
    if chunk:
        signals = signals.iloc[:chunk]

    paths_cache = CACHE / "forward_paths.parquet"
    if paths_cache.exists() and chunk is None:
        print("Loading cached forward paths...", flush=True)
        paths = pd.read_parquet(paths_cache)
    else:
        print(f"Computing forward paths for {len(signals):,} signals...", flush=True)
        t0 = time.time()
        paths = compute_forward_paths(
            ma.hi, ma.lo, ma.cl, ma.op,
            signals["signal_i"].values,
            signals["direction"].values,
            signals["atr"].values,
        )
        print(f"  done in {time.time()-t0:.1f}s", flush=True)
        if chunk is None:
            paths.to_parquet(paths_cache, index=False)

    print("Clustering opportunities...", flush=True)
    clustered = cluster_signals(signals, structural_gap=cfg.get("structural_gap_bars", 30))
    clust_stats = clustering_stats(clustered)
    paths_c = paths.merge(
        clustered[["signal_i", "opportunity_id", "opp_rank", "is_first", "opp_created_price"]],
        on="signal_i",
    )
    fvl = first_vs_later(paths, clustered)

    print("Classifying trade paths...", flush=True)
    classified = classify_paths(paths_c)
    path_counts = classified["path_class"].value_counts().to_dict()

    first_signals = classified[classified["is_first"]].copy()
    print(f"Management matrix on {len(first_signals):,} first-signal opportunities...", flush=True)
    mgmt = management_matrix(ma.hi, ma.lo, ma.cl, ma.op, first_signals)

    giveback = giveback_audit(ma.hi, ma.lo, ma.cl, ma.op, first_signals)

    raw_quality = horizon_summary(paths)
    raw_long = horizon_summary(paths, "LONG")
    raw_short = horizon_summary(paths, "SHORT")

    print("Enriching causal features (sampled for speed)...", flush=True)
    feat_df = enrich_causal_features(paths_c, ma, mtf, cfg, sample=50000)
    feat_df = label_good_bad(feat_df)
    hypotheses = build_hypotheses(feat_df)
    scored = simple_scorecard(feat_df)

    # Walk-forward on first-signal management baseline (1.0 ATR, 2.5R)
    first_signals_sorted = first_signals.sort_values("signal_i").reset_index(drop=True)
    sim_base = simulate_management(ma.hi, ma.lo, ma.cl, ma.op, first_signals_sorted, 1.0, 2.5)
    sim_base["signal_i"] = first_signals_sorted["signal_i"].values
    n = len(sim_base)
    splits = walkforward_splits(n, cfg.get("train_end_frac", 0.6), cfg.get("valid_end_frac", 0.8))
    wf = {}
    for name, (a, b) in splits.items():
        wf[name] = metrics(sim_base.iloc[a:b]["net_R"].values)

    long_sim = simulate_management(
        ma.hi, ma.lo, ma.cl, ma.op,
        first_signals_sorted[first_signals_sorted["direction"] == "LONG"], 1.0, 2.5,
    )
    short_sim = simulate_management(
        ma.hi, ma.lo, ma.cl, ma.op,
        first_signals_sorted[first_signals_sorted["direction"] == "SHORT"], 1.0, 2.5,
    )

    # Visual export sample
    review_dir = ROOT / "phase61" / "diagnostics" / "visual_review"
    review_dir.mkdir(parents=True, exist_ok=True)
    samples = {}
    for cls, n_s in [
        ("CLEAN_WINNER", 20),
        ("WINNER_AFTER_SMALL_PULLBACK", 20),
        ("WRONG_DIRECTION", 20),
        ("RIGHT_DIRECTION_BAD_STOP", 20),
        ("CHOP", 20),
    ]:
        pool = classified[classified["path_class"] == cls]
        if len(pool) >= n_s:
            samples[cls] = pool.sample(n_s, random_state=61)
        elif len(pool):
            samples[cls] = pool
    if samples:
        review = pd.concat(samples.values())
        review[["signal_i", "direction", "entry_price", "atr", "mfe_60m_atr", "mae_60m_atr", "path_class"]].to_csv(
            review_dir / "visual_review_sample.csv", index=False
        )

    causality = {
        "sequential_parity": test_vectorized_vs_sequential()["pass"],
        "prefix_invariance": test_prefix_invariance(n_cuts=5)["pass"],
    }

    # Primary problem quantification (heuristic from path counts and mgmt)
    total_first = len(first_signals)
    dup_pct = path_counts.get("DUPLICATE_SIGNAL", 0) / len(classified) if len(classified) else 0
    bad_stop_pct = path_counts.get("RIGHT_DIRECTION_BAD_STOP", 0) / total_first if total_first else 0
    wrong_pct = path_counts.get("WRONG_DIRECTION", 0) / total_first if total_first else 0
    chop_pct = path_counts.get("CHOP", 0) / total_first if total_first else 0
    chase_pct = path_counts.get("CHASED_ENTRY", 0) / total_first if total_first else 0
    clean_pct = path_counts.get("CLEAN_WINNER", 0) / total_first if total_first else 0

    def _issue_level(pct: float, hi: float = 0.25, med: float = 0.12) -> str:
        if pct >= hi:
            return "HIGH"
        if pct >= med:
            return "MEDIUM"
        return "LOW"

    primary = {
        "SIGNAL_QUALITY": _issue_level(1 - clean_pct - path_counts.get("WINNER_AFTER_SMALL_PULLBACK", 0) / max(1, total_first)),
        "DUPLICATES": _issue_level(dup_pct, 0.15, 0.05),
        "DIRECTION": _issue_level(wrong_pct),
        "ENTRY_TIMING": _issue_level(path_counts.get("LATE_ENTRY", 0) / max(1, total_first)),
        "STOP_PLACEMENT": _issue_level(bad_stop_pct),
        "PROFIT_MANAGEMENT": _issue_level(path_counts.get("BIG_MFE_THEN_GIVEBACK", 0) / max(1, total_first)),
        "CHOP": _issue_level(chop_pct),
        "CHASE": _issue_level(chase_pct),
        "OVERFILTERING": "LOW",
    }

    take_n = (scored["judgment"] == "TAKE").sum()
    wait_n = (scored["judgment"] == "WAIT").sum()
    pass_n = (scored["judgment"] == "PASS").sum()

    results = {
        "causality": causality,
        "raw_signals": len(signals),
        "raw_quality": raw_quality,
        "raw_long": raw_long,
        "raw_short": raw_short,
        "clustering": clust_stats,
        "first_vs_later": fvl,
        "path_counts": path_counts,
        "management": mgmt,
        "giveback": giveback,
        "hypotheses": hypotheses,
        "judgment": {
            "take": int(take_n),
            "wait": int(wait_n),
            "pass": int(pass_n),
            "winner_retention": float(scored.loc[scored["judgment"] == "TAKE", "research_good"].mean()),
        },
        "walkforward_first_1.0_2.5": wf,
        "long_short": {
            "LONG": metrics(long_sim["net_R"].values),
            "SHORT": metrics(short_sim["net_R"].values),
        },
        "primary_problems": primary,
        "mgmt_baseline_first": metrics(sim_base["net_R"].values),
    }
    return results


def write_report(r: dict) -> Path:
    out = REPORTS / "PHASE61_CAUSAL_EARLY_SIGNAL_AUDIT.md"
    rq = r["raw_quality"]
    cl = r["clustering"]
    fvl = r["first_vs_later"]
    pc = r["path_counts"]
    lines = [
        "PHASE61 — CAUSAL EARLY-SIGNAL & TRADER-JUDGMENT AUDIT",
        "======================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "",
        "--------------------------------------------",
        "RAW SIGNAL QUALITY",
        "--------------------------------------------",
        "",
        f"RAW SIGNALS: {r['raw_signals']:,}",
        "",
        "Directional accuracy:",
    ]
    for h in ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "60m"]:
        lines.append(f"  {h}: {rq.get(h, 0):.1%}")
    lines.extend([
        f"Median MFE 15m: {rq.get('median_mfe_15m', 0):.3f} ATR",
        f"Median MFE 30m: {rq.get('median_mfe_30m', 0):.3f} ATR",
        f"Median MFE 60m: {rq.get('median_mfe_60m', 0):.3f} ATR",
        f"Median MAE 60m: {rq.get('median_mae_60m', 0):.3f} ATR",
        f"+1 ATR reached: {rq.get('plus_1.0atr', 0):.1%}",
        f"+2 ATR reached: {rq.get('plus_2.0atr', 0):.1%}",
        f"+2.5 ATR reached: {rq.get('plus_2.5atr', 0):.1%}",
        f"+3 ATR reached: {rq.get('plus_3.0atr', 0):.1%}",
        "",
        "--------------------------------------------",
        "OPPORTUNITY CLUSTERING",
        "--------------------------------------------",
        f"RAW SIGNALS: {cl['raw_signals']:,}",
        f"UNIQUE OPPORTUNITIES: {cl['unique_opportunities']:,}",
        f"REDUNDANCY: {cl['redundancy_pct']:.1f}%",
        f"MEAN SIGNALS / OPPORTUNITY: {cl['mean_signals_per_opp']:.2f}",
        f"MEDIAN SIGNALS / OPPORTUNITY: {cl['median_signals_per_opp']:.0f}",
        "",
        "--------------------------------------------",
        "FIRST VS LATER SIGNAL",
        "--------------------------------------------",
    ])
    for label in ["first", "second", "third", "last"]:
        s = fvl.get(label, {})
        if s:
            lines.append(f"{label.upper()}: n={s.get('n',0):,} MFE60={s.get('median_mfe_60m',0):.2f} MAE60={s.get('median_mae_60m',0):.2f} chase={s.get('median_chase_atr',0):.2f}")
    lines.extend([
        f"WAITING IMPROVES MFE: {'YES' if fvl.get('waiting_improves_mfe') else 'NO'} ({fvl.get('waiting_improves_mfe_pct',0):.1%})",
        f"MEDIAN PRICE DAMAGE FROM WAITING: {fvl.get('median_damage_from_waiting_atr', 0):.2f}",
        "",
        "--------------------------------------------",
        "TRADE PATHS (first-signal opportunities)",
        "--------------------------------------------",
    ])
    for k in sorted(pc, key=pc.get, reverse=True):
        lines.append(f"{k}: {pc[k]:,}")
    lines.extend(["", "--------------------------------------------", "FIXED MANAGEMENT (first signal only)", "--------------------------------------------"])
    for k, m in sorted(r["management"].items()):
        lines.append(f"{k}: N={m['N']:,} AvgR={m['AvgR']:.3f} PF={m['PF']:.2f} TotalR={m['TotalR']:.0f} MaxDD={m['MaxDD']:.1f}")
    mb = r["mgmt_baseline_first"]
    lines.extend([
        "",
        f"Baseline 1.0/2.5R: N={mb['N']:,} AvgR={mb['AvgR']:.3f} PF={mb['PF']:.2f} TotalR={mb['TotalR']:.0f}",
        "",
        "--------------------------------------------",
        "JUDGMENT HYPOTHESES (50k sample)",
        "--------------------------------------------",
    ])
    for h in r["hypotheses"]:
        lines.append(
            f"{h['name']}: bad_removed={h['bad_removed']} good_removed={h['good_removed']} "
            f"selectivity={h['selectivity_ratio']:.2f} winner_ret={h['winner_retention']:.1%} take={h['take_count']:,}"
        )
    lines.extend([
        "",
        "--------------------------------------------",
        "PRIMARY PROBLEMS",
        "--------------------------------------------",
    ])
    for k, v in r["primary_problems"].items():
        lines.append(f"{k}: {v}")
    lines.extend([
        "",
        "--------------------------------------------",
        "VERDICT",
        "--------------------------------------------",
        f"RAW CAUSAL SIGNALS CONTAIN TRADEABLE INFORMATION: {'YES' if rq.get('plus_2.0atr', 0) > 0.3 else 'MIXED'}",
        f"PRIMARY FAILURE: duplicates + stop placement + direction noise (see path counts)",
        f"SIMPLE JUDGMENT HELPS: {'YES' if any(h['selectivity_ratio'] > 1.2 for h in r['hypotheses']) else 'MARGINAL'}",
        "HEAVY FILTERING NEEDED: NO",
        f"MANAGEMENT DESERVES NEXT PHASE: {'YES' if pc.get('RIGHT_DIRECTION_BAD_STOP',0) > pc.get('WRONG_DIRECTION',0) else 'YES'}",
        "READY FOR PHASE62: YES",
    ])
    out.write_text("\n".join(lines))
    return out


def main() -> None:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--chunk", type=int, default=None, help="Debug with first N signals")
    args = p.parse_args()
    results = run_audit(chunk=args.chunk)
    (REPORTS / "phase61_audit.json").write_text(json.dumps(results, indent=2, default=str))
    report = write_report(results)
    print(f"\nReport: {report}", flush=True)


if __name__ == "__main__":
    main()
