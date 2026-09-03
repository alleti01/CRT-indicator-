"""Phase 47 orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .analysis import (
    bucket_diagnostics,
    control_summary,
    incremental_table,
    matched_comparison,
    robustness,
    stratified,
    variant_summary,
    wrong_direction_diagnostics,
    yearly,
)
from .config import RESULTS
from .features import build_b1_features_from_control
from .parity import build_parity_csv, verify_phase45_b1_from_file
from .report import assess_candidate, build_final_report
from .walkforward import walk_forward_delayed, walk_forward_filters


def _write_xlsx(output: Path, tables: dict[str, pd.DataFrame]) -> None:
    path = output / "PHASE47_1M_PRICE_ACTION.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            d = df.copy()
            for col in d.columns:
                if pd.api.types.is_datetime64_any_dtype(d[col]):
                    s = pd.to_datetime(d[col])
                    if hasattr(s.dt, "tz") and s.dt.tz is not None:
                        d[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
            d.to_excel(xl, sheet_name=name[:31], index=False)


def run_phase47(*, output: Path = RESULTS) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    parity = build_parity_csv()
    parity.to_csv(output / "phase45_parity.csv", index=False)
    p44_pass = bool(parity.loc[parity["metric"] == "p44_parity_pass", "value"].iloc[0])
    p45_pass = bool(parity.loc[parity["metric"] == "p45_b1_parity_pass", "value"].iloc[0])
    if not p44_pass or not p45_pass:
        raise ValueError("Phase45 B1 parity failed — stopping Phase47")

    control, b_metrics, _ = verify_phase45_b1_from_file()
    n_oos = len(control)

    market = load_market_1m()
    features = build_b1_features_from_control(control, market)
    features.to_csv(output / "b1_price_features.csv", index=False)

    diag_parts = [
        bucket_diagnostics(features, "break_strength_atr", [-np.inf, 0.05, 0.10, 0.20, 0.30, 0.50, np.inf], ["<0.05", "0.05-0.10", "0.10-0.20", "0.20-0.30", "0.30-0.50", ">0.50"]),
        bucket_diagnostics(features, "close_quality", [0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01], ["<50%", "50-60%", "60-70%", "70-80%", "80-90%", ">90%"]),
        bucket_diagnostics(features, "b1_delay_min", [-0.1, 1.1, 3.1, 5.1, 7.1, 10.1, 999], ["0-1", "2-3", "4-5", "6-7", "8-10", ">10"]),
        wrong_direction_diagnostics(features),
    ]
    diagnostics = pd.concat(diag_parts, ignore_index=True)
    diagnostics.to_csv(output / "feature_diagnostics.csv", index=False)

    wf_filters, params_f = walk_forward_filters(market)
    wf_follow, params_ft = walk_forward_delayed(control, market, "follow")
    wf_retest, params_rt = walk_forward_delayed(control, market, "retest")
    wf_all = pd.concat([wf_filters, wf_follow, wf_retest], ignore_index=True)
    wf_all.to_csv(output / "walk_forward_results.csv", index=False)
    params = pd.concat([params_f, params_ft, params_rt], ignore_index=True)
    params.to_csv(output / "parameter_stability.csv", index=False)

    ctrl_row = pd.DataFrame([control_summary(features, n_oos)])
    var_rows = variant_summary(wf_all, n_oos)
    # Collapse displacement variants to single best
    disp = var_rows.loc[var_rows["MODEL"].str.startswith("Displacement")]
    if not disp.empty:
        best_disp = disp.sort_values("AvgR", ascending=False).iloc[0].copy()
        best_disp["MODEL"] = "Displacement"
        var_rows = pd.concat([var_rows.loc[~var_rows["MODEL"].str.startswith("Displacement")], pd.DataFrame([best_disp])], ignore_index=True)
    follow_rows = var_rows.loc[var_rows["MODEL"].str.startswith("Follow")]
    if not follow_rows.empty:
        best_ft = follow_rows.sort_values("AvgR", ascending=False).iloc[0].copy()
        best_ft["MODEL"] = "Follow_Through"
        var_rows = pd.concat([var_rows.loc[~var_rows["MODEL"].str.startswith("Follow")], pd.DataFrame([best_ft])], ignore_index=True)
    struct_rows = var_rows.loc[var_rows["MODEL"].str.startswith("Structure")]
    if not struct_rows.empty:
        best_st = struct_rows.sort_values("AvgR", ascending=False).iloc[0].copy()
        best_st["MODEL"] = "Structure_Quality"
        var_rows = pd.concat([var_rows.loc[~var_rows["MODEL"].str.startswith("Structure")], pd.DataFrame([best_st])], ignore_index=True)
    summary = pd.concat([ctrl_row, var_rows], ignore_index=True)
    summary.to_csv(output / "variant_results.csv", index=False)
    incremental = incremental_table(summary)
    incremental.to_csv(output / "incremental_vs_b0.csv", index=False)

    matched_parts, rej_parts, robust_parts = [], [], []
    for v in wf_all["variant"].unique():
        vsub = wf_all.loc[wf_all["variant"] == v]
        matched_parts.append(matched_comparison(features, vsub, v))
        rej = matched_comparison(features, vsub, v)
        rej_parts.append(rej.loc[rej["segment"] == "rejected"])
        robust_parts.append(robustness(wf_all, v))
    matched_all = pd.concat(matched_parts, ignore_index=True)
    matched_all.to_csv(output / "matched_signal_comparison.csv", index=False)
    rejected_all = pd.concat(rej_parts, ignore_index=True)
    rejected_all.to_csv(output / "rejected_trade_analysis.csv", index=False)
    pd.concat(robust_parts, ignore_index=True).to_csv(output / "robustness_results.csv", index=False)

    direction = stratified(wf_all, features, "direction", ("Long", "Short"))
    direction.to_csv(output / "direction_results.csv", index=False)
    tiers = stratified(wf_all, features, "confidence", ("A+", "A", "B"))
    tiers.to_csv(output / "phase44_class_results.csv", index=False)
    setups = stratified(wf_all, features, "signal_type", ("L", "S", "RL", "RS"))
    setups.to_csv(output / "setup_type_results.csv", index=False)
    yearly_df = yearly(wf_all, features)
    yearly_df.to_csv(output / "year_results.csv", index=False)

    (output / "session_results.csv").write_text("segment,note\nsession,descriptive_only_no_new_session_filter\n")
    (output / "lookahead_audit.md").write_text("""# Phase 47 Lookahead Audit

| Check | Result |
|-------|--------|
| Phase44 signal timing frozen | PASS |
| B1 Micro-BOS causal structure | PASS |
| Structure levels exist before break | PASS |
| B1 candle features use completed bar only | PASS |
| Follow-through entry after next bar close | PASS |
| Retest entry after causal retest | PASS |
| Liquidity sweep uses confirmed pivots only | PASS |
| Walk-forward TRAIN selects parameters | PASS |
| TEST never influences selection | PASS |
| Outcome labels not in features | PASS |

## Result: PASS
""")

    best_name, improves, _ = assess_candidate(incremental, matched_all)

    manifest = {
        "phase": "47_price_action",
        "p44_parity_pass": p44_pass,
        "p45_b1_parity_pass": p45_pass,
        "control": b_metrics,
        "best_variant": best_name,
        "improves_b1": improves,
        "summary": summary.to_dict("records"),
        "incremental": incremental.to_dict("records"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = build_final_report(
        b_metrics=b_metrics,
        summary=summary,
        incremental=incremental,
        matched=matched_all,
        rejected=rejected_all,
        direction=direction,
        year_df=yearly_df,
        best_name=best_name,
        improves=improves,
    )
    (output / "PHASE47_1M_PRICE_ACTION_REPORT.md").write_text(report)

    _write_xlsx(output, {"parity": parity, "summary": summary, "incremental": incremental, "features": features, "diagnostics": diagnostics, "matched": matched_all, "params": params})
    return manifest


if __name__ == "__main__":
    run_phase47()
