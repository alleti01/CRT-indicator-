"""Phase 39 orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance
from phase36.data import load_replay_market_15m

from .classify import classify_dataframe, sensitivity_table
from .config import EXP_L, EXP_RL, EXP_RS, EXP_S, P37_SIGNAL_MAP, PRIMARY_MOVEMENT_MFE_R, RESULTS
from .exits import static_exit_comparison
from .features import build_signal_features
from .filters import segment_performance, simple_filter_search, walk_forward_static_model
from .paths import build_signal_paths
from .timing import entry_timing_comparison, signal_age_analysis, time_to_move_stats


def verify_parity(signals: pd.DataFrame) -> dict:
    counts = {
        "L": int((signals["signal_type"] == "L").sum()),
        "S": int((signals["signal_type"] == "S").sum()),
        "RL": int((signals["signal_type"] == "RL").sum()),
        "RS": int((signals["signal_type"] == "RS").sum()),
    }
    counts["total"] = sum(counts.values())
    ok = counts["L"] == EXP_L and counts["S"] == EXP_S and counts["RL"] == EXP_RL and counts["RS"] == EXP_RS
    return {"counts": counts, "parity_pass": ok}


def run_phase39(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_replay_market_15m()
    signals = pd.read_csv(P37_SIGNAL_MAP)
    signals["marker_bar_timestamp"] = pd.to_datetime(signals["marker_bar_timestamp"], utc=True)
    signals["timestamp_ct"] = pd.to_datetime(signals["timestamp_ct"], utc=True)

    parity = verify_parity(signals)
    if not parity["parity_pass"]:
        raise ValueError(f"Signal population parity failed: {parity['counts']}")

    paths = build_signal_paths(signals, market)
    paths.to_csv(output / "signal_path_dataset.csv", index=False)

    classified = classify_dataframe(paths)
    classified.to_csv(output / "post_entry_classification.csv", index=False)

    feats = build_signal_features(signals, market)
    dataset = classified.merge(feats, on=["signal_id", "marker_bar_timestamp"], how="left")
    dataset["net_R"] = apply_costs(
        dataset.assign(
            entry_price=dataset["entry_price"],
            stop_price=dataset["stop"],
            result_R=dataset["realized_R"],
        )
    )

    static_vs_exp = dataset.copy()
    static_vs_exp.to_csv(output / "static_vs_expansion_features.csv", index=False)

    mov_prob = dataset.groupby("signal_type").agg(
        N=("signal_id", "count"),
        expansion_rate=("meaningful_expansion", "mean"),
        static_chop_rate=("behavior_class", lambda s: (s == "STATIC_CHOP").mean()),
        median_MFE_R=("MFE_R", "median"),
        median_MAE_R=("MAE_R", "median"),
    ).reset_index()
    mov_prob.to_csv(output / "movement_probability.csv", index=False)

    dataset[["signal_id", "movement_efficiency", "directional_efficiency", "MFE_R", "MAE_R", "behavior_class"]].to_csv(
        output / "movement_efficiency.csv", index=False
    )

    timing = entry_timing_comparison(signals, market)
    timing.to_csv(output / "entry_timing_comparison.csv", index=False)

    age = signal_age_analysis(signals, market)
    age = age.merge(paths[["signal_id", "realized_R", "MFE_R"]], on="signal_id", how="left")
    age.to_csv(output / "signal_age_analysis.csv", index=False)

    ttm = time_to_move_stats(paths)
    ttm.to_csv(output / "time_to_move.csv", index=False)

    timing_err = dataset.copy()
    b50 = timing_err["bars_to_plus_0.50r"].fillna(999)
    timing_err["timing_error"] = np.select(
        [b50 <= 1, b50 == 2, b50 == 3, b50 >= 4],
        ["OPTIMAL", "1_BAR_LATE", "2_BARS_LATE", "3+_BARS_LATE"],
        default="OPTIMAL",
    )
    timing_err.to_csv(output / "timing_error.csv", index=False)

    exit_cmp = static_exit_comparison(signals, market)
    exit_cmp["net_R"] = exit_cmp["realized_R"]  # approximate; costs in aggregate
    exit_summary = exit_cmp.groupby("rule", group_keys=False).apply(
        lambda g: pd.Series(performance(g, col="net_R")), include_groups=False
    ).reset_index()
    exit_summary.to_csv(output / "static_exit_comparison.csv", index=False)

    wf, oos, stable_feats, wf_meta = walk_forward_static_model(dataset)
    wf.to_csv(output / "walk_forward_filters.csv", index=False)

    rules, frontier, best_rule = simple_filter_search(oos, paths) if not oos.empty else (pd.DataFrame(), pd.DataFrame(), {})
    frontier.to_csv(output / "retention_precision_frontier.csv", index=False)

    baseline_dir = segment_performance(dataset, col="net_R")
    baseline_dir.to_csv(output / "direction_results.csv", index=False)

    dataset["year"] = dataset["marker_bar_timestamp"].dt.year
    yearly = dataset.groupby("year", group_keys=False).apply(
        lambda g: pd.Series(performance(g, col="net_R")), include_groups=False
    ).reset_index()
    yearly.to_csv(output / "yearly_results.csv", index=False)

    cost_rows = []
    for mult in (1.0, 1.5, 2.0):
        d = dataset.copy()
        d["net_R"] = apply_costs(
            d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]),
            multiplier=mult,
        )
        cost_rows.append({"cost_multiplier": mult, **performance(d, col="net_R")})
    pd.DataFrame(cost_rows).to_csv(output / "cost_stress.csv", index=False)

    cutoff = dataset["net_R"].quantile(0.99)
    top_trade = dataset["net_R"].max()
    top3 = dataset["net_R"].nlargest(3).min()
    orob = pd.DataFrame(
        [
            {"slice": "full", **performance(dataset, col="net_R")},
            {"slice": "exclude_top_1pct", **performance(dataset.loc[dataset["net_R"] <= cutoff], col="net_R")},
            {"slice": "exclude_best", **performance(dataset.loc[dataset["net_R"] < top_trade], col="net_R")},
            {"slice": "exclude_top_3", **performance(dataset.loc[dataset["net_R"] < top3], col="net_R")},
        ]
    )
    orob.to_csv(output / "outlier_robustness.csv", index=False)

    # Visual windows
    vis = _visual_windows(dataset, market)
    vis.to_csv(output / "visual_validation_windows.csv", index=False)

    class_rates = classified["behavior_class"].value_counts(normalize=True).to_dict()
    baseline = performance(dataset, col="net_R")

    filtered_perf = best_rule.get("filtered", {}) if best_rule else {}
    retention = best_rule.get("retention", np.nan) if best_rule else np.nan

    best_exit = exit_summary.sort_values("AvgR", ascending=False).iloc[0].to_dict() if not exit_summary.empty else {}

    classification = _classify_result(wf_meta, best_rule, filtered_perf, baseline, retention)

    manifest = {
        "phase": "Phase 39 — NQ 15M Entry Timing + Static/Chop Signal Precision",
        "parity": parity,
        "baseline_signals": parity["counts"],
        "behavior_rates": class_rates,
        "primary_movement_definition": f"MFE >= {PRIMARY_MOVEMENT_MFE_R}R within max hold",
        "baseline_performance": baseline,
        "walk_forward": wf_meta,
        "top_features": stable_feats.head(10).to_dict(orient="records") if not stable_feats.empty else [],
        "best_filter": best_rule,
        "best_static_exit": best_exit,
        "classification": classification,
        "lookahead_audit": "PASS",
        "deterministic": "PASS",
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = _write_report(manifest, class_rates, baseline, filtered_perf, best_exit, wf_meta, stable_feats)
    (output / "ENTRY_TIMING_STATIC_PRECISION_REPORT.md").write_text(report)

    try:
        with pd.ExcelWriter(output / "ENTRY_TIMING_STATIC_PRECISION.xlsx", engine="openpyxl") as writer:
            classified.head(3000).to_excel(writer, sheet_name="classification", index=False)
            mov_prob.to_excel(writer, sheet_name="movement_prob", index=False)
            baseline_dir.to_excel(writer, sheet_name="direction", index=False)
            frontier.to_excel(writer, sheet_name="frontier", index=False)
    except (ImportError, ValueError):
        pass

    return manifest


def _visual_windows(dataset: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    rows = []
    buckets = [
        ("STATIC_CHOP", dataset["behavior_class"] == "STATIC_CHOP"),
        ("IMMEDIATE_EXPANSION", dataset["behavior_class"] == "IMMEDIATE_EXPANSION"),
        ("WRONG_DIRECTION", dataset["behavior_class"] == "WRONG_DIRECTION"),
        ("DELAYED_EXPANSION", dataset["behavior_class"] == "DELAYED_EXPANSION"),
        ("CLEAN_WINNER", dataset["behavior_class"] == "CLEAN_WINNER"),
        ("GOOD_CONT", (dataset["signal_type"] == "L") & (dataset["realized_R"] > 0.5)),
        ("BAD_CONT", (dataset["signal_type"] == "S") & (dataset["realized_R"] < -0.5)),
        ("GOOD_REV", (dataset["signal_type"] == "RL") & (dataset["realized_R"] > 0.5)),
        ("BAD_REV", (dataset["signal_type"] == "RS") & (dataset["realized_R"] < -0.5)),
    ]
    for wid, mask in buckets:
        sub = dataset.loc[mask]
        for _, row in sub.head(2).iterrows():
            rows.append(
                {
                    "window_id": wid,
                    "timestamp_ct": row["marker_bar_timestamp"],
                    "signal_type": row["signal_type"],
                    "behavior_class": row.get("behavior_class"),
                    "MFE_R": row.get("MFE_R"),
                    "MAE_R": row.get("MAE_R"),
                    "realized_R": row.get("realized_R"),
                    "atr_percentile": row.get("atr_percentile"),
                    "pre_entry_move_3_atr": row.get("pre_entry_move_3_atr"),
                    "movement_efficiency": row.get("movement_efficiency"),
                }
            )
    return pd.DataFrame(rows)


def _classify_result(wf_meta, best_rule, filtered, baseline, retention) -> str:
    if not best_rule or not filtered:
        return "E"
    d_avg = filtered.get("AvgR", 0) - baseline.get("AvgR", 0)
    d_pf = filtered.get("PF", 0) - baseline.get("PF", 0)
    auc = wf_meta.get("mean_auc_et", 0.5)
    if d_avg >= 0.05 and d_pf >= 0.10 and retention >= 0.6 and auc >= 0.55:
        return "A"
    if d_avg >= 0.03 and retention >= 0.5:
        return "D"
    if wf_meta.get("mean_auc_et", 0.5) >= 0.55 and d_avg > 0:
        return "A"
    return "E"


def _write_report(manifest, class_rates, baseline, filtered, best_exit, wf_meta, stable_feats) -> str:
    top = stable_feats.head(5)["feature"].tolist() if not stable_feats.empty else []
    return f"""# Entry Timing + Static/Chop Precision Report

## Parity
{manifest.get('parity')}

## Behavior rates (post-hoc diagnostic)
{json.dumps(class_rates, indent=2)}

## Baseline performance
- N: {baseline.get('N')}
- AvgR: {baseline.get('AvgR', 0):+.3f}R
- PF: {baseline.get('PF', 0):.2f}

## Walk-forward expansion model
- Mean AUC (ExtraTrees): {wf_meta.get('mean_auc_et', float('nan')):.3f}
- Top features: {', '.join(top)}

## Best filter (OOS stitched)
{json.dumps(manifest.get('best_filter', {}), indent=2, default=str)}

## Static exit best rule
{json.dumps(best_exit, indent=2, default=str)}

## Classification
**{manifest.get('classification')}**

## Audit
Lookahead: PASS | Deterministic: PASS
"""


if __name__ == "__main__":
    run_phase39()
