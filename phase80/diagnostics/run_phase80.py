#!/usr/bin/env python3
"""Phase80 — universal causal confluence search (M0 frozen)."""
from __future__ import annotations

import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.walkforward_audit import walkforward_splits
from phase69.python.entry_freeze import config_hash
from phase80.python.combinations import (
    apply_validation,
    redundancy_matrix,
    role_gated_model,
    score_model,
    search_pairs,
    search_singles,
    search_triples,
)
from phase80.python.config import (
    BASELINE_AVG_R,
    BASELINE_N,
    CHECKPOINTS,
    EXPECTED_PINE_SHA256,
    EXPECTED_SIGNAL_HASH,
    MAX_FINALISTS,
    REPORTS,
    TRAIN_FRAC,
    VALID_FRAC,
    pine_sha256,
)
from phase80.python.evaluate import summarize_subset
from phase80.python.features import build_features, load_entry_stream, partition_slice, prefix_causality_check
from phase80.python.registry import excluded_dataframe, registry_dataframe

VETO_COLS = {
    "F_NO_HTF_CONTRA", "F_FALSE_REV_LOW", "F_NO_PULLBACK", "F_HTF_LTF_AGREE", "F_CT_LOW",
}


def _save_json(name: str, obj) -> None:
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    (CHECKPOINTS / name).write_text(json.dumps(obj, indent=2, default=str))


def _build_mask_from_row(row: pd.Series, df: pd.DataFrame) -> pd.Series:
    if row["logic_type"] == "SCORE":
        return df["CONFLUENCE_SCORE"] >= int(row["threshold"])
    if row["logic_type"] == "ROLE_GATED":
        loc = df["F_GOOD_LOCATION"] | df["F_LOCATION_SCORE"]
        react = df["F_REACTION_SCORE"] | df["F_REVERSAL_STRONG"]
        veto = df["F_NO_HTF_CONTRA"] & df["F_FALSE_REV_LOW"] & df["F_NO_PULLBACK"]
        return loc & react & veto
    cols = [c for c in str(row["feature_cols"]).split("+") if c in df.columns]
    if row["logic_type"] == "VETO" and len(cols) >= 2:
        veto_col = next(c for c in cols if c in VETO_COLS)
        other_col = next(c for c in cols if c != veto_col)
        return df[other_col].astype(bool) & ~df[veto_col].astype(bool)
    mask = df[cols[0]].astype(bool)
    for c in cols[1:]:
        mask &= df[c].astype(bool)
    return mask


def main() -> int:
    t0 = time.time()
    REPORTS.mkdir(parents=True, exist_ok=True)

    ph = pine_sha256()
    if ph != EXPECTED_PINE_SHA256:
        print("PHASE80_BASELINE_REPRODUCTION_FAIL")  # also signal freeze fail
        print("Pine hash mismatch")
        return 2

    sh = config_hash()
    if sh != EXPECTED_SIGNAL_HASH:
        print("PHASE80_EXACT_SIGNAL_STREAM_UNAVAILABLE")
        return 2

    df = load_entry_stream()
    baseline = summarize_subset(df)
    if abs(baseline["AvgR"] - BASELINE_AVG_R) > 1e-6 or baseline["N"] != BASELINE_N:
        _save_json("00_baseline_fail.json", {"expected": BASELINE_AVG_R, "got": baseline["AvgR"], "N": baseline["N"]})
        print("PHASE80_BASELINE_REPRODUCTION_FAIL")
        return 2

    splits = walkforward_splits(len(df), TRAIN_FRAC, VALID_FRAC)
    df, thresholds = build_features(df, splits["train"])
    causal = prefix_causality_check(df)

    registry_dataframe().to_csv(REPORTS / "COMPONENT_REGISTRY.csv", index=False)
    excluded_dataframe().to_csv(REPORTS / "EXCLUDED_COMPONENTS.csv", index=False)

    # Singles / pairs / triples on TRAIN
    singles = search_singles(df, splits)
    pairs = search_pairs(df, splits, VETO_COLS)
    triples = search_triples(df, splits)
    scores = score_model(df, splits)
    role_gated = role_gated_model(df, splits)

    all_train = pd.concat([singles, pairs, triples, scores, role_gated], ignore_index=True)
    all_train["partition"] = "train"

    # Validation pass on top finalists
    val = apply_validation(all_train, df, splits, top_n=MAX_FINALISTS)
    merged = all_train.merge(val, on="model_id", how="left")

    # Holdout for survivors only
    survivors = val[val["validation_pass"] == True]["model_id"].tolist()  # noqa: E712
    holdout_rows = []
    for mid in survivors[:5]:
        row = merged[merged["model_id"] == mid].iloc[0]
        mask = _build_mask_from_row(row, df)
        ho = summarize_subset(df.iloc[splits["holdout"][0]:splits["holdout"][1]], mask.iloc[splits["holdout"][0]:splits["holdout"][1]])
        base_ho = summarize_subset(df.iloc[splits["holdout"][0]:splits["holdout"][1]])
        holdout_rows.append({"model_id": mid, **ho, "DeltaAvgR_holdout": ho.get("AvgR", 0) - base_ho.get("AvgR", 0)})
    holdout_df = pd.DataFrame(holdout_rows)

    merged.to_csv(REPORTS / "ALL_COMBINATIONS.csv", index=False)
    redundancy_matrix(df).to_csv(REPORTS / "REDUNDANCY_MATRIX.csv", index=False)

    # Incremental value per component
    inc_rows = []
    base_train = summarize_subset(partition_slice(df, splits["train"]))
    for col in singles["feature_cols"].unique():
        s = singles[singles["feature_cols"] == col]
        if len(s):
            inc_rows.append({
                "component": col,
                "standalone_AvgR": s.iloc[0]["AvgR"],
                "standalone_DeltaAvgR": s.iloc[0]["DeltaAvgR"],
                "retention": s.iloc[0]["retention"],
            })
    pd.DataFrame(inc_rows).to_csv(REPORTS / "COMPONENT_INCREMENTAL_VALUE.csv", index=False)

    # Best summaries
    best_single = singles.sort_values("DeltaAvgR", ascending=False).head(1)
    best_pair = pairs.sort_values("DeltaAvgR", ascending=False).head(1)
    best_triple = triples.sort_values("DeltaAvgR", ascending=False).head(1)
    best_score = scores.sort_values("DeltaAvgR", ascending=False).head(1)
    best_train = merged.sort_values("DeltaAvgR", ascending=False).head(1)
    best_val = val.sort_values("DeltaAvgR_validation", ascending=False).head(1) if len(val) else pd.DataFrame()

    n_hyp = len(all_train)
    any_val_pass = bool(survivors)
    best_val_delta = float(best_val.iloc[0]["DeltaAvgR_validation"]) if len(best_val) else -999

    if not causal["pass"]:
        verdict = "PHASE80_CAUSALITY_FAIL"
    elif not any_val_pass:
        verdict = "PHASE80_VALIDATION_FAIL" if best_train.iloc[0]["DeltaAvgR"] > 0 else "PHASE80_NO_INCREMENTAL_EDGE"
    elif best_val_delta > 0.01:
        verdict = "PHASE80_SIMPLE_MODEL_PASS" if best_val.iloc[0]["complexity"] <= 3 else "PHASE80_CONFLUENCE_PASS"
    else:
        # Check if best is location/activity only
        top = best_train.iloc[0]
        if "LOCATION" in top["roles"] and "REACTION" not in top["roles"]:
            verdict = "PHASE80_LOCATION_INFORMATION_ONLY"
        elif top["random_control_result"] < 0.005:
            verdict = "PHASE80_ACTIVITY_INFORMATION_ONLY"
        else:
            verdict = "PHASE80_NO_INCREMENTAL_EDGE"

    _save_json("00_baseline.json", baseline)
    _save_json("01_thresholds.json", thresholds)
    _save_json("02_causality.json", causal)
    _save_json("18_final.json", {"verdict": verdict, "hypotheses_tested": n_hyp, "validation_survivors": len(survivors)})

    lines = [
        "# Phase80 — Universal Causal Confluence Search",
        "",
        f"**VERDICT:** `{verdict}`",
        "",
        "**RESEARCH ENTRY STREAM:** `PHASE60`",
        "",
        "**PHASE72A_HISTORICAL_PARITY_NOT_ESTABLISHED** — Phase72A Pine is production signal authority; Phase60 is historical causal research anchor.",
        "",
        f"**Pine SHA256:** `{ph}`",
        f"**Signal hash:** `{sh}`",
        "",
        "## BASELINE (M0 frozen, net R)",
        f"- N: {baseline['N']:,}",
        f"- AvgR: {baseline['AvgR']:.6f}",
        f"- PF: {baseline['PF']:.3f}",
        f"- TotalR: {baseline['TotalR']:.1f}",
        f"- MaxDD: {baseline['MaxDD']:.1f}",
        "",
        f"**ELIGIBLE COMPONENTS:** {len(singles)} singles (entry-time Phase60 fields)",
        f"**EXCLUDED COMPONENTS:** see EXCLUDED_COMPONENTS.csv",
        f"**TOTAL HYPOTHESES TESTED:** {n_hyp:,}",
        "",
        "## BEST TRAIN",
        f"- Single: {best_single.iloc[0]['model_id'] if len(best_single) else 'N/A'} ΔAvgR={best_single.iloc[0]['DeltaAvgR']:.4f}" if len(best_single) else "",
        f"- Pair: {best_pair.iloc[0]['model_id'] if len(best_pair) else 'N/A'} ΔAvgR={best_pair.iloc[0]['DeltaAvgR']:.4f}" if len(best_pair) else "",
        f"- Triple: {best_triple.iloc[0]['model_id'] if len(best_triple) else 'N/A'} ΔAvgR={best_triple.iloc[0]['DeltaAvgR']:.4f}" if len(best_triple) else "",
        f"- Score: {best_score.iloc[0]['model_id'] if len(best_score) else 'N/A'} ΔAvgR={best_score.iloc[0]['DeltaAvgR']:.4f}" if len(best_score) else "",
        "",
        "## VALIDATION",
        f"- Survivors (ΔAvgR>0, N≥200): **{len(survivors)}**",
        f"- Best validation ΔAvgR: **{best_val_delta:.4f}**" if len(best_val) else "- No validation survivors",
        "",
        "## Multiple-hypothesis warning",
        f"Tested {n_hyp:,} combinations on train; train-best is NOT trustworthy without validation. Validation survivors: {len(survivors)}.",
        "",
        "## M0 (frozen)",
        "STOP=1.0R, TARGET=2.5R, MAX_HOLD=60m, STOP_FIRST, cost=$14.50 RT",
        "",
        f"Completed in {time.time()-t0:.1f}s",
    ]
    (REPORTS / "PHASE80_FINAL_REPORT.md").write_text("\n".join(lines) + "\n")

    if survivors:
        top_id = survivors[0]
        row = merged[merged["model_id"] == top_id].iloc[0]
        _save_json("PHASE80_CANDIDATE_FREEZE.json", {
            "model_id": top_id,
            "components": row["feature_cols"],
            "logic": row["logic_type"],
            "thresholds": thresholds,
            "train_metrics": row.to_dict(),
            "validation": val[val["model_id"] == top_id].iloc[0].to_dict() if top_id in val["model_id"].values else {},
        })

    print(verdict)
    print(f"Hypotheses={n_hyp} val_survivors={len(survivors)} best_train_DeltaAvgR={best_train.iloc[0]['DeltaAvgR']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
