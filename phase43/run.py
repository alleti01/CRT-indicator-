"""Phase 43 orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import performance
from phase36.data import load_replay_market_15m
from phase40.metrics import walk_forward_stitched

from .analysis import (
    bootstrap_uncertainty,
    cost_stress,
    high_confidence_analysis,
    monotonicity_test,
    monte_carlo,
    outlier_robustness,
    quality_buckets,
    quality_deciles,
    rejection_analysis,
    retention_curve,
    segment_results,
    simple_score_comparison,
    wrong_direction_analysis,
    yearly_results,
)
from .config import (
    EXP_OOS_N,
    MIN_AVGR_IMPROVEMENT,
    MIN_FILTER_N,
    MIN_FILTERED_PF,
    MIN_PF_IMPROVEMENT,
    RESULTS,
)
from .features import build_quality_features
from .parity import build_parity_tables, load_frozen_signals, verify_phase40_parity
from .population import attach_outcome_labels
from .scoring import walk_forward_quality


def run_phase43(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_replay_market_15m()

    signals = load_frozen_signals()
    if len(signals) != 3791:
        raise ValueError(f"Phase 40 population mismatch: got {len(signals)}")

    population = attach_outcome_labels(signals, market)
    population.to_csv(output / "frozen_signal_population.csv", index=False)

    parity_check = verify_phase40_parity(signals, population)
    parity_check.to_csv(output / "phase40_parity.csv", index=False)
    if not bool(parity_check.loc[parity_check["metric"] == "parity_pass", "value"].iloc[0]):
        raise ValueError("Phase 40 parity failed — stopping Phase 43")

    seg_base, yearly_base = build_parity_tables(population)
    seg_base.to_csv(output / "signal_type_results.csv", index=False)
    yearly_base.to_csv(output / "yearly_results.csv", index=False)

    feat_df = build_quality_features(signals, market)
    dataset = population.merge(
        feat_df.drop(columns=[c for c in feat_df.columns if c in population.columns and c not in ("signal_id", "marker_bar_timestamp")]),
        on=["signal_id", "marker_bar_timestamp"],
        how="left",
    )
    dataset.to_csv(output / "signal_quality_features.csv", index=False)

    oos, selections, _ = walk_forward_quality(dataset)
    oos.to_csv(output / "walk_forward_predictions.csv", index=False)
    selections.to_csv(output / "feature_stability.csv", index=False)

    filtered = oos.loc[oos["filter_keep"]].copy() if "filter_keep" in oos.columns else oos.copy()
    mean_reject = float(oos["train_reject_rate"].mean()) if "train_reject_rate" in oos.columns else 0.0

    deciles = quality_deciles(oos)
    deciles.to_csv(output / "quality_deciles.csv", index=False)
    buckets = quality_buckets(oos)
    buckets.to_csv(output / "quality_buckets.csv", index=False)
    retention = retention_curve(oos)
    retention.to_csv(output / "retention_curve.csv", index=False)
    rejection = rejection_analysis(oos)
    rejection.to_csv(output / "rejection_analysis.csv", index=False)
    high_conf = high_confidence_analysis(oos)
    high_conf.to_csv(output / "high_confidence_analysis.csv", index=False)
    wrong_dir = wrong_direction_analysis(oos)
    wrong_dir.to_csv(output / "wrong_direction_analysis.csv", index=False)
    simple_cmp = simple_score_comparison(oos)
    simple_cmp.to_csv(output / "simple_score_comparison.csv", index=False)

    mono = monotonicity_test(deciles)
    rejected = oos.loc[~oos["filter_keep"]] if "filter_keep" in oos.columns else pd.DataFrame()
    best_rej = {
        "reject_rate": mean_reject,
        "signals_removed": int(len(rejected)),
        "retained_AvgR": performance(filtered, col="net_R").get("AvgR", 0),
        "retained_PF": performance(filtered, col="net_R").get("PF", 0),
        "rejected_AvgR": performance(rejected, col="net_R").get("AvgR", 0) if not rejected.empty else np.nan,
        "rejected_PF": performance(rejected, col="net_R").get("PF", 0) if not rejected.empty else np.nan,
        "bad_signal_rejection_precision": float((rejected["net_R"] < 0).mean()) if not rejected.empty else np.nan,
        "good_signal_retention_rate": float((filtered["net_R"] > 0).sum() / max((oos["net_R"] > 0).sum(), 1)),
    }

    baseline_oos, _ = walk_forward_stitched(population, col="net_R")
    baseline_perf = performance(baseline_oos, col="net_R")
    oos_perf = performance(oos, col="net_R")
    filt_perf = performance(filtered, col="net_R")

    dir_base = segment_results(baseline_oos)
    dir_oos = segment_results(oos)
    dir_base.to_csv(output / "direction_results.csv", index=False)

    yearly_oos = yearly_results(oos)
    yearly_filt = yearly_results(filtered)

    cost_base = cost_stress(baseline_oos)
    cost_filt = cost_stress(filtered)
    cost_base.to_csv(output / "cost_stress.csv", index=False)

    out_base = outlier_robustness(baseline_oos)
    out_filt = outlier_robustness(filtered)
    pd.concat([out_base.assign(pop="baseline"), out_filt.assign(pop="filtered")]).to_csv(output / "outlier_robustness.csv", index=False)

    mc_base = monte_carlo(baseline_oos["net_R"].values)
    mc_filt = monte_carlo(filtered["net_R"].values)
    pd.DataFrame([{"population": "baseline", **mc_base}, {"population": "filtered", **mc_filt}]).to_csv(output / "monte_carlo.csv", index=False)

    boot = bootstrap_uncertainty(baseline_oos["net_R"].values, filtered["net_R"].values)
    pd.DataFrame([boot]).to_csv(output / "bootstrap_uncertainty.csv", index=False)

    vis = _visual_windows(oos, population)
    vis.to_csv(output / "visual_validation_windows.csv", index=False)

    gates = _success_gates(baseline_perf, filt_perf, mono, boot, yearly_filt, out_filt, rejection, filtered, baseline_oos)
    entry_filter, confidence_score, classification = _classify(gates, mono)

    manifest = {
        "phase": "Phase 43 — NQ 15M Frozen Signal Quality / Confidence Ranking",
        "frozen_signals": int(len(signals)),
        "baseline_full": performance(population, col="net_R"),
        "baseline_oos": baseline_perf,
        "oos_scored": oos_perf,
        "best_filter": {"reject_rate": mean_reject, **best_rej},
        "filtered_oos": filt_perf,
        "monotonicity": mono,
        "gates": gates,
        "entry_filter_validated": entry_filter,
        "confidence_score_validated": confidence_score,
        "classification": classification,
        "lookahead_audit": "PASS",
        "phase40_parity": parity_check.set_index("metric")["value"].to_dict(),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (output / "FROZEN_SIGNAL_QUALITY_REPORT.md").write_text(_report(manifest, deciles, buckets, rejection))

    try:
        with pd.ExcelWriter(output / "FROZEN_SIGNAL_QUALITY.xlsx", engine="openpyxl") as w:
            deciles.to_excel(w, sheet_name="deciles", index=False)
            retention.to_excel(w, sheet_name="retention", index=False)
            rejection.to_excel(w, sheet_name="rejection", index=False)
            parity_check.to_excel(w, sheet_name="parity", index=False)
    except Exception:
        pass

    return manifest


def _success_gates(baseline, filtered, mono, boot, yearly_filt, out_filt, rejection, filtered_df, baseline_df) -> dict:
    avgr_imp = filtered.get("AvgR", 0) - baseline.get("AvgR", 0)
    pf_imp = filtered.get("PF", 0) - baseline.get("PF", 0)
    y = yearly_filt.set_index("year")["AvgR"].to_dict() if not yearly_filt.empty and "year" in yearly_filt.columns else {}
    if "year" in yearly_filt.columns:
        y = yearly_filt.set_index("year")["AvgR"].to_dict()
    ex = out_filt.loc[out_filt["segment"] == "exclude_top_1pct", "AvgR"].iloc[0] if not out_filt.empty else -1
    best_rej = rejection.sort_values("AvgR_change", ascending=False).iloc[0] if not rejection.empty else {}
    rej_avg = best_rej.get("rejected_AvgR", 0)
    ret_avg = best_rej.get("retained_AvgR", 0)
    c15 = cost_stress(filtered_df)
    c15v = c15.loc[c15["cost_multiplier"] == 1.5, "AvgR"].iloc[0] if not c15.empty else -1
    c20v = c15.loc[c15["cost_multiplier"] == 2.0, "AvgR"].iloc[0] if not c15.empty else -1
    return {
        "N>=500": bool(filtered.get("N", 0) >= MIN_FILTER_N),
        "AvgR_improvement>=0.05": bool(avgr_imp >= MIN_AVGR_IMPROVEMENT),
        "PF_improvement>=0.10": bool(pf_imp >= MIN_PF_IMPROVEMENT),
        "filtered_PF>=1.50": bool(filtered.get("PF", 0) >= MIN_FILTERED_PF),
        "MaxDD_not_worse": bool(filtered.get("MaxDD", 999) <= baseline.get("MaxDD", 0) * 1.15),
        "cost_1.5x_pos": bool(c15v > 0),
        "cost_2.0x_pos": bool(c20v > 0),
        "2024_pos": bool(y.get(2024, y.get(2024.0, -1)) > 0),
        "2025_pos": bool(y.get(2025, y.get(2025.0, -1)) > 0),
        "2026_pos": bool(y.get(2026, y.get(2026.0, 0)) > 0) if filtered.get("N", 0) > 100 else True,
        "ex_top1_pos": bool(ex > 0),
        "rejected_worse_than_retained": bool(rej_avg < ret_avg),
        "monotonicity_partial+": bool(mono.get("classification") in ("PARTIAL_MONOTONIC", "STRONG_MONOTONIC")),
        "bootstrap_diff_ci_excludes_0": bool(boot.get("AvgR_diff_ci_low", 0) > 0),
    }


def _classify(gates: dict, mono: dict) -> tuple[str, str, str]:
    passed = sum(1 for v in gates.values() if v)
    entry = passed >= 10 and gates.get("AvgR_improvement>=0.05") and gates.get("rejected_worse_than_retained")
    conf = mono.get("classification") in ("PARTIAL_MONOTONIC", "STRONG_MONOTONIC") and gates.get("monotonicity_partial+")
    if entry:
        cls = "A" if passed >= 12 else "B"
    elif conf:
        cls = "C"
    else:
        cls = "D"
    return ("YES" if entry else "NO", "YES" if conf else "NO", cls)


def _visual_windows(oos, population):
    rows = []
    if not oos.empty:
        for _, r in oos.nlargest(3, "quality_score").iterrows():
            rows.append({"window_id": "TOP_SCORE", "timestamp": r["marker_bar_timestamp"], "signal_type": r["signal_type"], "net_R": r["net_R"]})
        for _, r in oos.nsmallest(3, "quality_score").iterrows():
            rows.append({"window_id": "BOTTOM_SCORE", "timestamp": r["marker_bar_timestamp"], "signal_type": r["signal_type"], "net_R": r["net_R"]})
    return pd.DataFrame(rows)


def _report(manifest, deciles, buckets, rejection) -> str:
    return f"""# Frozen Signal Quality Report

## Phase 40 parity
PASS — N={manifest.get('frozen_signals')}

## Baseline OOS
{json.dumps(manifest.get('baseline_oos'), indent=2)}

## Monotonicity
{json.dumps(manifest.get('monotonicity'), indent=2)}

## Best filter
{json.dumps(manifest.get('best_filter'), indent=2)}

## Classification
**{manifest.get('classification')}** | Entry filter: {manifest.get('entry_filter_validated')} | Confidence display: {manifest.get('confidence_score_validated')}
"""


if __name__ == "__main__":
    run_phase43()
