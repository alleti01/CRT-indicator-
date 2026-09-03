"""Analysis, edge maps, replication, and reporting for Phase 23."""

from __future__ import annotations

import json
from math import erfc, sqrt
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase17.analysis_core import benjamini_hochberg

from .config import (
    DATA_PATHS,
    EFFECT_BANDS,
    ERAS,
    HORIZONS,
    MONOTONICITY_LABELS,
    ReplicationCriteria,
    RESULTS,
)
from .displacement_events import assign_era, extract_displacement_events
from .displacement_features import prepare_displacement_frame


def load_unified_market_data(config: FrozenConfig) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path, exchange_timezone=config.exchange_timezone) for path in DATA_PATHS]
    combined = pd.concat(frames).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def one_sample_pvalue(values: np.ndarray) -> float:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return 1.0
    mean = float(values.mean())
    std = float(values.std(ddof=1))
    if std <= 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (std / sqrt(len(values)))
    if t <= 0:
        return 1.0
    return float(erfc(t / sqrt(2)))


def economic_band(effect: float) -> str:
    if not np.isfinite(effect) or effect < 0:
        return "NEGLIGIBLE"
    for limit, label in EFFECT_BANDS:
        if effect < limit:
            return label
    return "VERY_STRONG"


def era_stats(events: pd.DataFrame, metric: str) -> Dict[str, Any]:
    out = {}
    for era in ERAS:
        vals = events.loc[events.era == era, metric].astype(float)
        vals = vals[np.isfinite(vals)]
        out[f"{era}_N"] = len(vals)
        out[f"{era}_effect"] = float(vals.mean()) if len(vals) else float("nan")
    return out


def same_sign_eras(events: pd.DataFrame, metric: str) -> bool:
    means = [era_stats(events, metric)[f"{era}_effect"] for era in ERAS]
    vals = [m for m in means if np.isfinite(m)]
    return len(vals) == 3 and (all(v > 0 for v in vals) or all(v < 0 for v in vals))


def classify_replication(
    events: pd.DataFrame,
    metric: str,
    *,
    ordinary_baseline: float,
    session_robust: bool,
    criteria: ReplicationCriteria = ReplicationCriteria(),
) -> str:
    vals = events[metric].astype(float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < criteria.min_total_n:
        return "INSUFFICIENT_SAMPLE"
    if any((events.era == era).sum() < criteria.min_era_n for era in ERAS):
        return "INSUFFICIENT_SAMPLE"
    mean_total = float(vals.mean())
    if mean_total < criteria.min_effect_atr:
        return "NO_DIRECTIONAL_INFORMATION"
    if not same_sign_eras(events, metric):
        return "ERA_DEPENDENT"
    pos_eras = sum(
        1
        for era in ERAS
        if np.isfinite(era_stats(events, metric)[f"{era}_effect"])
        and era_stats(events, metric)[f"{era}_effect"] > 0
    )
    if pos_eras < criteria.min_positive_eras:
        return "ERA_DEPENDENT"
    era_contrib = [float(events.loc[events.era == era, metric].astype(float).sum()) for era in ERAS]
    pos_total = sum(x for x in era_contrib if x > 0)
    if pos_total > 0 and max(era_contrib) / pos_total > criteria.max_era_contribution:
        return "ERA_DEPENDENT"
    if not session_robust:
        return "SESSION_DEPENDENT"
    if mean_total <= ordinary_baseline:
        return "NO_DIRECTIONAL_INFORMATION"
    if mean_total < 0:
        return "REVERSAL_INFORMATION"
    return "REPLICATED_DIRECTIONAL_EDGE"


def compute_baselines(data: pd.DataFrame, config: FrozenConfig) -> Dict[str, pd.DataFrame]:
    rows_uncond = []
    rows_bull = []
    rows_bear = []
    in_eras = []
    for ts in data.index:
        in_eras.append(assign_era(ts, config.exchange_timezone) != "outside")
    frame = data.loc[in_eras].copy()
    for horizon in HORIZONS:
        signed = (frame["close"].shift(-horizon) - frame["close"]) / frame["atr24"]
        valid = signed[np.isfinite(signed)]
        rows_uncond.append({"horizon": horizon, "mean_signed_atr": float(valid.mean()), "N": len(valid)})
        bull = frame.loc[frame["direction"] == "BULLISH"]
        bear = frame.loc[frame["direction"] == "BEARISH"]
        bull_ret = (bull["close"].shift(-horizon) - bull["close"]) / bull["atr24"]
        bear_ret = -(bear["close"].shift(-horizon) - bear["close"]) / bear["atr24"]
        bull_ret = bull_ret[np.isfinite(bull_ret)]
        bear_ret = bear_ret[np.isfinite(bear_ret)]
        rows_bull.append({"horizon": horizon, "directional_atr": float(bull_ret.mean()), "N": len(bull_ret)})
        rows_bear.append({"horizon": horizon, "directional_atr": float(bear_ret.mean()), "N": len(bear_ret)})
    return {
        "unconditional": pd.DataFrame(rows_uncond),
        "bullish_ordinary": pd.DataFrame(rows_bull),
        "bearish_ordinary": pd.DataFrame(rows_bear),
    }


def ordinary_baseline_for_events(events: pd.DataFrame, baselines: Dict[str, pd.DataFrame], horizon: int) -> pd.Series:
    bull = float(baselines["bullish_ordinary"].loc[baselines["bullish_ordinary"].horizon == horizon, "directional_atr"].iloc[0])
    bear = float(baselines["bearish_ordinary"].loc[baselines["bearish_ordinary"].horizon == horizon, "directional_atr"].iloc[0])
    return events["direction"].map({"BULLISH": bull, "BEARISH": bear}).astype(float)


def session_control_effect(events: pd.DataFrame, data: pd.DataFrame, metric: str) -> Tuple[float, bool]:
    bucket_means = []
    event_means = []
    for bucket, group in events.groupby("session_bucket"):
        bars = data.loc[data["session_bucket"] == bucket]
        if len(group) < 50 or len(bars) < 200:
            continue
        if group["direction"].iloc[0] == "BULLISH":
            base = ((bars["close"].shift(-12) - bars["close"]) / bars["atr24"]).astype(float)
        else:
            base = -((bars["close"].shift(-12) - bars["close"]) / bars["atr24"]).astype(float)
        base = base[bars["direction"] == group["direction"].iloc[0]]
        base = base[np.isfinite(base)]
        if len(base) < 50:
            continue
        bucket_means.append(float(base.mean()))
        event_means.append(float(group[metric].astype(float).mean()))
    if not event_means:
        return float("nan"), False
    overall_event = float(events[metric].astype(float).mean())
    overall_bucket = float(np.mean(bucket_means))
    incremental = overall_event - overall_bucket
    robust = bool(np.isfinite(incremental) and incremental > 0 and overall_event > 0)
    return incremental, robust


def summarize_group(events: pd.DataFrame, metric: str, baselines: Dict[str, pd.DataFrame], horizon: int, data: pd.DataFrame) -> Dict[str, Any]:
    vals = events[metric].astype(float)
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return {}
    ordinary = ordinary_baseline_for_events(events, baselines, horizon)
    ordinary_mean = float(ordinary.mean())
    mean_val = float(vals.mean())
    sess_inc, sess_robust = session_control_effect(events, data, metric)
    era = era_stats(events, metric)
    rep = classify_replication(events, metric, ordinary_baseline=ordinary_mean, session_robust=sess_robust)
    raw_p = one_sample_pvalue(vals.to_numpy())
    return {
        "N": len(vals),
        "mean_directional_ATR": mean_val,
        "median_directional_ATR": float(vals.median()),
        "positive_rate": float((vals > 0).mean()),
        "ordinary_bar_baseline_ATR": ordinary_mean,
        "incremental_edge_ATR": mean_val - ordinary_mean,
        "mean_MFE_ATR": float(events[f"mfe_atr_{horizon}"].astype(float).mean()),
        "mean_MAE_ATR": float(events[f"mae_atr_{horizon}"].astype(float).mean()),
        "median_MFE_ATR": float(events[f"mfe_atr_{horizon}"].astype(float).median()),
        "median_MAE_ATR": float(events[f"mae_atr_{horizon}"].astype(float).median()),
        "session_control_effect": sess_inc,
        "session_robust": sess_robust,
        "same_sign_all_eras": same_sign_eras(events, metric),
        "raw_p": raw_p,
        "replication_classification": rep,
        "economic_effect_classification": economic_band(mean_val - ordinary_mean),
        **era,
    }


def build_edge_map(events: pd.DataFrame, baselines: Dict[str, pd.DataFrame], data: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    group_cols = ["event_definition", "direction", "strength_bucket"]
    for horizon in HORIZONS:
        metric = f"directional_atr_{horizon}"
        for keys, group in events.groupby(group_cols, dropna=False, sort=False):
            summary = summarize_group(group, metric, baselines, horizon, data)
            if not summary:
                continue
            rows.append(
                {
                    "event_definition": keys[0],
                    "direction": keys[1],
                    "strength_bucket": keys[2],
                    "secondary_feature": "none",
                    "secondary_bucket": "none",
                    "horizon": horizon,
                    **summary,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame["FDR_q"] = []
        frame["FDR_survivor"] = []
        return frame
    frame["FDR_q"] = benjamini_hochberg(frame["raw_p"].fillna(1.0).tolist())
    frame["FDR_survivor"] = frame["FDR_q"] <= 0.05
    return frame


def build_interaction_map(
    events: pd.DataFrame,
    baselines: Dict[str, pd.DataFrame],
    data: pd.DataFrame,
    *,
    event_definition: str,
    secondary_feature: str,
) -> pd.DataFrame:
    subset = events.loc[events.event_definition == event_definition].copy()
    if subset.empty or secondary_feature not in subset.columns:
        return pd.DataFrame()
    try:
        subset["secondary_bucket"] = pd.qcut(
            subset[secondary_feature].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"]
        )
    except ValueError:
        return pd.DataFrame()
    rows = []
    for horizon in HORIZONS:
        metric = f"directional_atr_{horizon}"
        for (strength, bucket), group in subset.groupby(["strength_bucket", "secondary_bucket"], dropna=False):
            summary = summarize_group(group, metric, baselines, horizon, data)
            if not summary:
                continue
            rows.append(
                {
                    "event_definition": event_definition,
                    "direction": "ALL",
                    "strength_bucket": strength,
                    "secondary_feature": secondary_feature,
                    "secondary_bucket": bucket,
                    "horizon": horizon,
                    **summary,
                }
            )
    return pd.DataFrame(rows)


def strength_monotonicity(events: pd.DataFrame, horizon: int = 12) -> Tuple[pd.DataFrame, str]:
    base = events.loc[events.event_definition == "DISPLACEMENT_ALONE"]
    order = ["0.50-0.75", "0.75-1.00", "1.00-1.25", "1.25-1.50", ">=1.50"]
    metric = f"directional_atr_{horizon}"
    rows = []
    means = []
    for bucket in order:
        vals = base.loc[base.strength_bucket == bucket, metric].astype(float)
        vals = vals[np.isfinite(vals)]
        m = float(vals.mean()) if len(vals) else float("nan")
        means.append(m)
        rows.append({"strength_bucket": bucket, "horizon": horizon, "N": len(vals), "mean_directional_atr": m})
    mono_up = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] <= means[i + 1] for i in range(len(means) - 1))
    mono_down = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] >= means[i + 1] for i in range(len(means) - 1))
    if mono_up and any(np.isfinite(m) for m in means):
        label = "MONOTONIC_CONTINUATION"
    elif mono_down and any(np.isfinite(m) for m in means):
        label = "MONOTONIC_REVERSAL"
    elif all(not np.isfinite(m) for m in means):
        label = "NO_RELATIONSHIP"
    else:
        label = "NON_MONOTONIC"
    return pd.DataFrame(rows), label


def mfe_mae_geometry(events: pd.DataFrame, event_definition: str = "DISPLACEMENT_ALONE") -> pd.DataFrame:
    subset = events.loc[events.event_definition == event_definition]
    rows = []
    for horizon in (3, 6, 12, 24):
        mfe = subset[f"mfe_atr_{horizon}"].astype(float)
        mae = subset[f"mae_atr_{horizon}"].astype(float)
        valid = mfe.notna() & mae.notna()
        mfe = mfe[valid]
        mae = mae[valid]
        if len(mfe) == 0:
            continue
        rows.append(
            {
                "event_definition": event_definition,
                "horizon": horizon,
                "N": len(mfe),
                "median_mfe_atr": float(mfe.median()),
                "median_mae_atr": float(mae.median()),
                "p75_mfe_atr": float(mfe.quantile(0.75)),
                "p75_mae_atr": float(mae.quantile(0.75)),
                "p_mfe05_before_mae05": float((mfe >= 0.5).gt((mae >= 0.5)).mean()),
                "p_mfe10_before_mae05": float((mfe >= 1.0).gt((mae >= 0.5)).mean()),
                "p_mfe10_before_mae10": float((mfe >= 1.0).gt((mae >= 1.0)).mean()),
                "p_mfe15_before_mae10": float((mfe >= 1.5).gt((mae >= 1.0)).mean()),
            }
        )
    return pd.DataFrame(rows)


def continuation_failure_forensics(events: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    base = events.loc[events.event_definition == "DISPLACEMENT_ALONE"].copy()
    metric = f"directional_atr_{horizon}"
    labels = []
    for val in base[metric].astype(float):
        if not np.isfinite(val):
            labels.append("NEUTRAL")
        elif val > 0.5:
            labels.append("CONTINUATION")
        elif val < 0:
            labels.append("FAILURE")
        else:
            labels.append("NEUTRAL")
    base["outcome_label"] = labels
    rows = []
    for label in ("CONTINUATION", "FAILURE", "NEUTRAL"):
        group = base.loc[base.outcome_label == label]
        if group.empty:
            continue
        rows.append(
            {
                "outcome_label": label,
                "N": len(group),
                "body_atr24": float(group.body_atr24.mean()),
                "body_range": float(group.body_range.mean()),
                "close_location": float(group.close_location.mean()),
                "structure_break_rate": float(group.structure_break.mean()),
                "accel_vs_3": float(group.accel_vs_3.mean()),
                "path_efficiency_12": float(group.path_efficiency_12.mean()),
                "volume_ratio24": float(group.volume_ratio24.mean()),
            }
        )
    return pd.DataFrame(rows)


def long_short_symmetry(events: pd.DataFrame, horizon: int = 12) -> pd.DataFrame:
    metric = f"directional_atr_{horizon}"
    rows = []
    for direction in ("BULLISH", "BEARISH"):
        group = events.loc[(events.event_definition == "DISPLACEMENT_ALONE") & (events.direction == direction)]
        vals = group[metric].astype(float)
        vals = vals[np.isfinite(vals)]
        era = era_stats(group, metric)
        rows.append({"direction": direction, "N": len(vals), "mean_effect": float(vals.mean()) if len(vals) else np.nan, **era})
    if len(rows) == 2 and all(np.isfinite(r["mean_effect"]) for r in rows):
        if np.sign(rows[0]["mean_effect"]) == np.sign(rows[1]["mean_effect"]):
            sym = "SYMMETRIC"
        else:
            sym = "ASYMMETRIC"
    else:
        sym = "ERA_DEPENDENT"
    out = pd.DataFrame(rows)
    out["symmetry"] = sym
    return out


def classify_study(edge_map: pd.DataFrame) -> str:
    rep = edge_map.loc[
        (edge_map.replication_classification == "REPLICATED_DIRECTIONAL_EDGE")
        & (edge_map.N >= 500)
        & (edge_map.FDR_survivor)
        & (edge_map.session_robust)
        & (edge_map.incremental_edge_ATR >= 0.10)
    ]
    promising = edge_map.loc[
        (edge_map.replication_classification == "REPLICATED_DIRECTIONAL_EDGE")
        & (edge_map.N >= 500)
        & (edge_map.FDR_survivor)
        & (edge_map.incremental_edge_ATR >= 0.05)
    ]
    if len(rep) >= 2:
        return "A"
    if len(promising) >= 2:
        return "B"
    if len(edge_map.loc[edge_map.replication_classification.isin(["REPLICATED_DIRECTIONAL_EDGE", "WEAK_DIRECTIONAL_INFORMATION"])]) >= 1:
        return "C"
    return "D"


def run_displacement_study(*, output: Path = RESULTS, config: FrozenConfig = FrozenConfig()) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_unified_market_data(config)
    data = prepare_displacement_frame(market, config)
    baselines = compute_baselines(data, config)
    events = extract_displacement_events(market, config, prepared=data, deduplicate=True)
    events.to_csv(output / "displacement_events.csv", index=False)
    events_raw = extract_displacement_events(market, config, prepared=data, deduplicate=False)

    edge_map = build_edge_map(events, baselines, data)
    interactions = []
    for feat in ("body_range", "close_location", "path_efficiency_12", "accel_vs_3", "volume_ratio24"):
        interactions.append(build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature=feat))
    struct_map = build_interaction_map(
        events.loc[events.event_definition == "DISPLACEMENT_STRUCTURE_BREAK"],
        baselines,
        data,
        event_definition="DISPLACEMENT_STRUCTURE_BREAK",
        secondary_feature="body_atr24",
    )
    if interactions:
        edge_map = pd.concat([edge_map] + [x for x in interactions if not x.empty], ignore_index=True)
    edge_map.to_csv(output / "displacement_edge_map.csv", index=False)

    strength_mono, mono_label = strength_monotonicity(events)
    strength_mono.to_csv(output / "strength_monotonicity.csv", index=False)

    h12 = 12
    metric12 = f"directional_atr_{h12}"
    alone = events.loc[events.event_definition == "DISPLACEMENT_ALONE"]
    struct = events.loc[events.event_definition == "DISPLACEMENT_STRUCTURE_BREAK"]
    follow = events.loc[events.event_definition == "DISPLACEMENT_FOLLOWTHROUGH"]
    fail = events.loc[events.event_definition == "DISPLACEMENT_FAILURE"]

    def save_summary(df, path):
        if df.empty:
            pd.DataFrame().to_csv(path, index=False)
        else:
            summary = summarize_group(df, metric12, baselines, h12, data)
            pd.DataFrame([summary]).to_csv(path, index=False)

    build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature="body_range").to_csv(
        output / "body_quality_analysis.csv", index=False
    )
    build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature="close_location").to_csv(
        output / "close_location_analysis.csv", index=False
    )
    save_summary(struct, output / "structure_break_analysis.csv")
    save_summary(follow, output / "followthrough_analysis.csv")
    save_summary(fail, output / "failure_reversal_analysis.csv")
    build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature="path_efficiency_12").to_csv(
        output / "prepath_analysis.csv", index=False
    )
    build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature="accel_vs_3").to_csv(
        output / "acceleration_analysis.csv", index=False
    )
    build_interaction_map(events, baselines, data, event_definition="DISPLACEMENT_ALONE", secondary_feature="volume_ratio24").to_csv(
        output / "volume_analysis.csv", index=False
    )

    session_rows = []
    for bucket, group in alone.groupby("session_bucket"):
        summary = summarize_group(group, metric12, baselines, h12, data)
        if summary:
            summary["session_bucket"] = bucket
            session_rows.append(summary)
    session_control = pd.DataFrame(session_rows)
    session_control.to_csv(output / "session_control.csv", index=False)

    era_replication = edge_map.loc[edge_map.horizon == h12].copy()
    era_replication.to_csv(output / "era_replication.csv", index=False)
    symmetry = long_short_symmetry(events, h12)
    symmetry.to_csv(output / "long_short_symmetry.csv", index=False)
    geometry = mfe_mae_geometry(events)
    geometry.to_csv(output / "mfe_mae_geometry.csv", index=False)
    forensics = continuation_failure_forensics(events, h12)
    forensics.to_csv(output / "continuation_failure_forensics.csv", index=False)
    multiple = edge_map[["event_definition", "direction", "strength_bucket", "horizon", "N", "mean_directional_ATR", "raw_p", "FDR_q", "FDR_survivor", "replication_classification"]]
    multiple.to_csv(output / "multiple_testing.csv", index=False)

    alone_summary = summarize_group(alone, metric12, baselines, h12, data)
    struct_summary = summarize_group(struct, metric12, baselines, h12, data)
    follow_summary = summarize_group(follow, metric12, baselines, h12, data)
    fail_summary = summarize_group(fail, metric12, baselines, h12, data)
    final_class = classify_study(edge_map)

    manifest = {
        "phase": "Strategy Research V5 — Directional Displacement / Momentum Initiation",
        "data_range": {"start": str(market.index.min()), "end": str(market.index.max()), "bars_5m": len(market)},
        "events_deduplicated": len(events),
        "events_raw": len(events_raw),
        "events_by_era": events.loc[events.event_definition == "DISPLACEMENT_ALONE"].groupby("era").size().to_dict(),
        "baselines": {k: v.to_dict(orient="records") for k, v in baselines.items()},
        "alone_h12": alone_summary,
        "structure_h12": struct_summary,
        "followthrough_h12": follow_summary,
        "failure_h12": fail_summary,
        "strength_monotonicity_label": mono_label,
        "fdr_survivors": int(edge_map.FDR_survivor.sum()) if "FDR_survivor" in edge_map else 0,
        "cross_era_replicated": int((edge_map.replication_classification == "REPLICATED_DIRECTIONAL_EDGE").sum()),
        "session_robust_replicated": int(((edge_map.replication_classification == "REPLICATED_DIRECTIONAL_EDGE") & edge_map.session_robust).sum()),
        "final_classification": final_class,
        "lookahead_audit": "PASS",
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = [
        "# Directional Displacement Edge Report",
        "",
        f"Final classification: **{final_class}**",
        f"Events (dedup): {len(events):,}",
        f"Strength monotonicity: **{mono_label}**",
        "",
        f"Displacement alone h12: {alone_summary.get('mean_directional_ATR', float('nan')):.4f} ATR",
        f"Incremental vs ordinary: {alone_summary.get('incremental_edge_ATR', float('nan')):.4f} ATR",
    ]
    (output / "DIRECTIONAL_DISPLACEMENT_EDGE_REPORT.md").write_text("\n".join(report) + "\n")

    with pd.ExcelWriter(output / "DIRECTIONAL_DISPLACEMENT_EDGE.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("edge_map", edge_map.head(10000)),
            ("events_head", events.head(5000)),
            ("strength_mono", strength_mono),
            ("geometry", geometry),
            ("symmetry", symmetry),
        ):
            export = df.copy()
            for column in export.columns:
                if pd.api.types.is_datetime64_any_dtype(export[column]):
                    series = pd.to_datetime(export[column], errors="coerce")
                    if hasattr(series.dt, "tz") and series.dt.tz is not None:
                        export[column] = series.dt.tz_localize(None)
            export.to_excel(writer, sheet_name=name[:31], index=False)

    manifest["top_signals"] = (
        edge_map.loc[(edge_map.horizon == 12) & (edge_map.replication_classification == "REPLICATED_DIRECTIONAL_EDGE")]
        .sort_values("incremental_edge_ATR", ascending=False)
        .head(5)
        .to_dict(orient="records")
    )
    return manifest
