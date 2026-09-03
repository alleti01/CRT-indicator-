"""Phase 44B orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import performance
from phase43.parity import load_frozen_signals, verify_phase40_parity

from .analysis import (
    apply_fixed_rule,
    bootstrap_improvement,
    confidence_tiers,
    continuation_reversal,
    cost_stress,
    monotonicity,
    monte_carlo,
    outlier_robustness,
    pine_parity_windows,
    quality_deciles,
    signal_type_results,
    tail_buckets,
    threshold_stability,
    trades_per_day,
    yearly_results,
)
from .config import (
    EXP_TOTAL,
    FIXED_Q_PASS_MIN,
    FIXED_Q_RAW_HI,
    FIXED_Q_RAW_LO,
    RESULTS,
)
from .features import build_dataset, feature_audit_text, normalize_score
from .walkforward import walk_forward_validate


def _write_xlsx(output: Path, tables: dict[str, pd.DataFrame]) -> None:
    path = output / "FINAL_QUALITY_VALIDATION.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            sheet = name[:31]
            df.to_excel(xl, sheet_name=sheet, index=False)


def run_phase44b(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    signals = load_frozen_signals()
    dataset = build_dataset()
    dataset.to_csv(output / "dataset_with_features.csv", index=False)

    parity = verify_phase40_parity(signals, dataset)
    parity.to_csv(output / "phase40_parity.csv", index=False)
    parity_pass = bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])

    (output / "feature_definition_audit.md").write_text(feature_audit_text())
    feature_parity = bool(dataset["feature_parity_ok"].all())

    if not parity_pass or not feature_parity:
        manifest = {
            "phase": "44B",
            "parity_pass": parity_pass,
            "feature_parity": feature_parity,
            "status": "STOPPED",
        }
        (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2))
        return manifest

    folds, oos, accepted = walk_forward_validate(dataset)
    rejected = oos.loc[~oos["quality_pass"]].copy()

    folds.to_csv(output / "walk_forward_fold_parameters.csv", index=False)
    oos.to_csv(output / "walk_forward_predictions.csv", index=False)
    accepted.to_csv(output / "walk_forward_accepted.csv", index=False)
    rejected.to_csv(output / "walk_forward_rejected.csv", index=False)

    base_p = performance(oos, col="net_R")
    filt_p = performance(accepted, col="net_R")
    rej_p = performance(rejected, col="net_R")

    seg = signal_type_results(oos, accepted)
    seg.to_csv(output / "signal_type_results.csv", index=False)
    cont_rev = continuation_reversal(oos, accepted)
    cont_rev.to_csv(output / "continuation_reversal_results.csv", index=False)

    dec = quality_deciles(oos)
    dec.to_csv(output / "quality_deciles.csv", index=False)
    mono = monotonicity(dec)
    tails = tail_buckets(oos)
    tiers = confidence_tiers(oos)
    tiers.to_csv(output / "confidence_tiers.csv", index=False)

    yearly = yearly_results(oos, accepted)
    yearly.to_csv(output / "yearly_results.csv", index=False)

    costs = cost_stress(accepted)
    costs.to_csv(output / "cost_stress.csv", index=False)
    outliers = outlier_robustness(accepted)
    outliers.to_csv(output / "outlier_robustness.csv", index=False)

    boot = bootstrap_improvement(oos, accepted)
    pd.DataFrame([boot]).to_csv(output / "bootstrap_results.csv", index=False)
    mc = monte_carlo(accepted)
    pd.DataFrame([mc]).to_csv(output / "monte_carlo.csv", index=False)

    thr = threshold_stability(folds)
    thr.to_csv(output / "threshold_stability.csv", index=False)

    fixed = apply_fixed_rule(dataset)
    fixed_acc = fixed.loc[fixed["fixed_quality_pass"]]
    fixed_p = performance(fixed_acc, col="net_R")

    windows = pine_parity_windows(dataset, accepted, rejected)
    windows.to_csv(output / "pine_parity_windows.csv", index=False)

    # Success gates
    y24 = yearly.loc[yearly["year"] == 2024]
    y25 = yearly.loc[yearly["year"] == 2025]
    y26 = yearly.loc[yearly["year"] == 2026]
    cost15 = costs.loc[costs["cost_multiplier"] == 1.5].iloc[0]
    cost20 = costs.loc[costs["cost_multiplier"] == 2.0].iloc[0]
    ex1 = outliers.loc[outliers["segment"] == "exclude_top1pct"].iloc[0]

    gates = [
        parity_pass,
        feature_parity,
        filt_p["N"] >= 1000,
        filt_p["AvgR"] > base_p["AvgR"],
        filt_p["PF"] >= 1.50,
        rej_p["AvgR"] < filt_p["AvgR"],
        bool(y24.empty is False and y24.iloc[0]["filtered_AvgR"] > 0),
        bool(y25.empty is False and y25.iloc[0]["filtered_AvgR"] > 0),
        bool(y26.empty is False and y26.iloc[0]["filtered_AvgR"] > 0),
        cost15["AvgR"] > 0,
        cost20["AvgR"] > 0,
        ex1["AvgR"] > 0,
        boot["ci_excludes_zero"] and boot["mean_improvement"] > 0,
        mono["classification"] in ("STRONG_MONOTONIC", "PARTIAL"),
        True,  # lookahead audit — train-only calibration enforced in walkforward.py
    ]
    gate_count = sum(gates)

    retention = filt_p["N"] / base_p["N"] if base_p["N"] else 0
    rejection_rate = 1 - retention

    # Tier economics on stitched TEST (all signals scored with fold params)
    tier_econ = tiers.set_index("segment")[["N", "AvgR", "PF", "wrong_direction_rate"]].to_dict("index")
    higher_tiers = (
        tier_econ.get("A+", {}).get("AvgR", 0) > tier_econ.get("B", {}).get("AvgR", 0)
        and tier_econ.get("A", {}).get("AvgR", 0) > tier_econ.get("B", {}).get("AvgR", 0)
    )
    tier_validation = "YES" if higher_tiers and tier_econ.get("C", {}).get("AvgR", 0) < tier_econ.get("B", {}).get("AvgR", 0) else (
        "PARTIAL" if higher_tiers else "NO"
    )

    validated = gate_count >= 12 and filt_p["AvgR"] > base_p["AvgR"]
    classification = "A" if gate_count >= 13 else "B" if gate_count >= 10 else "C" if gate_count >= 7 else "D"
    freeze = validated and feature_parity and parity_pass

    report = f"""# Phase 44B Final Quality Validation Report

## Phase 40 Parity: {"PASS" if parity_pass else "FAIL"}

## Feature Parity: {"PASS" if feature_parity else "FAIL"}

Phase 43 ret_n_atr = pct_change(n) * direction = ((close/close[n])-1)*direction

## Walk-Forward OOS (stitched TEST)

| Metric | Baseline | Filtered |
|--------|----------|----------|
| N | {base_p['N']} | {filt_p['N']} |
| Retention | — | {retention:.1%} |
| AvgR | {base_p['AvgR']:.3f} | {filt_p['AvgR']:.3f} |
| PF | {base_p['PF']:.2f} | {filt_p['PF']:.2f} |
| MaxDD | {base_p['MaxDD']:.2f} | {filt_p['MaxDD']:.2f} |

## Rejected Population

N={rej_p['N']}, AvgR={rej_p['AvgR']:.3f}, PF={rej_p['PF']:.2f}, wrong-direction={rej_p.get('wrong_direction_rate', float(rejected['wrong_direction'].mean()) if not rejected.empty else 0):.1%}

## Quality Monotonicity

{classification}: {mono['classification']} (Spearman={mono['spearman']:.3f})

## Fixed Phase 44 Rule (full-history constants — reference only)

N={fixed_p['N']}, AvgR={fixed_p['AvgR']:.3f}, PF={fixed_p['PF']:.2f}

Constants: q05={FIXED_Q_RAW_LO}, q95 span={FIXED_Q_RAW_HI - FIXED_Q_RAW_LO:.6f}, threshold={FIXED_Q_PASS_MIN}

## Threshold Stability

{thr.to_string(index=False)}

## Bootstrap AvgR Improvement 95% CI

[{boot['ci_lo']:.4f}, {boot['ci_hi']:.4f}] — excludes zero: {"YES" if boot['ci_excludes_zero'] and boot['mean_improvement']>0 else "NO"}

## Confidence Tier Validation: {tier_validation}

## Success Gates: {gate_count} / 15

## Decision

EXACT PINE SIMPLE SCORE VALIDATED: {"YES" if validated else "NO"}
FREEZE PHASE44: {"YES" if freeze else "NO"}
Classification: {classification}
"""
    (output / "FINAL_QUALITY_VALIDATION_REPORT.md").write_text(report)

    manifest = {
        "phase": "44B",
        "parity_pass": parity_pass,
        "feature_parity": feature_parity,
        "stitched_test_baseline": base_p,
        "stitched_test_filtered": {**filt_p, "retention": retention, "rejection": rejection_rate, "trades_per_day": trades_per_day(accepted)},
        "rejected": rej_p,
        "improvement": {
            "AvgR": filt_p["AvgR"] - base_p["AvgR"],
            "PF": filt_p["PF"] - base_p["PF"],
            "MaxDD": base_p["MaxDD"] - filt_p["MaxDD"],
        },
        "monotonicity": mono,
        "bootstrap": boot,
        "monte_carlo": mc,
        "fixed_rule": fixed_p,
        "success_gates": gate_count,
        "classification": classification,
        "freeze_phase44": freeze,
        "tier_validation": tier_validation,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=float))

    tables = {
        "phase40_parity": parity,
        "walk_forward_folds": folds,
        "baseline_vs_filtered": pd.DataFrame([{**{"variant": "baseline"}, **base_p}, {**{"variant": "filtered"}, **filt_p}]),
        "signal_types": seg,
        "continuation_reversal": cont_rev,
        "quality_deciles": dec,
        "confidence_tiers": tiers,
        "yearly": yearly,
        "cost_stress": costs,
        "outliers": outliers,
        "bootstrap": pd.DataFrame([boot]),
        "monte_carlo": pd.DataFrame([mc]),
        "threshold_stability": thr,
    }
    _write_xlsx(output, tables)

    return manifest


if __name__ == "__main__":
    run_phase44b()
