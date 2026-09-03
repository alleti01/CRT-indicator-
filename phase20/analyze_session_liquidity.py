"""Aggregate analysis, edge map, and reporting for Phase 20."""

from __future__ import annotations

import json
from math import erfc, sqrt
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase17.analysis_core import benjamini_hochberg

from .config import (
    CONTAMINATED_WINDOWS,
    DATA_PATHS,
    ERAS,
    EVENT_TYPES,
    HORIZONS,
    LEVELS,
    RESULTS,
    ReplicationCriteria,
    TIME_BUCKETS,
)
from .session_events import assign_era, extract_session_liquidity_events


def load_unified_market_data(config: FrozenConfig) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path, exchange_timezone=config.exchange_timezone) for path in DATA_PATHS]
    combined = pd.concat(frames).sort_index()
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined


def sample_tier(n: int) -> str:
    if n < 100:
        return "INSUFFICIENT"
    if n < 300:
        return "WEAK_SAMPLE"
    return "ANALYZABLE"


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


def bootstrap_ci(values: np.ndarray, *, n: int = 1000, seed: int = 20) -> Tuple[float, float]:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(n)]
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def assign_displacement_quantile(events: pd.DataFrame, column: str = "body_atr") -> pd.Series:
    labels = pd.Series(index=events.index, dtype="object")
    for (_, _), group in events.groupby(["level", "event_type"], sort=False):
        valid = group[column].astype(float)
        valid = valid[np.isfinite(valid)]
        if len(valid) < 20:
            labels.loc[group.index] = "ALL"
            continue
        try:
            quantiles = pd.qcut(valid, 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")
        except ValueError:
            labels.loc[group.index] = "ALL"
            continue
        labels.loc[quantiles.index] = quantiles.astype(str)
    return labels.fillna("ALL")


def summarize_group(values: np.ndarray) -> Dict[str, float]:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    n = len(values)
    if n == 0:
        return {
            "N": 0,
            "mean": float("nan"),
            "median": float("nan"),
            "positive_rate": float("nan"),
            "stderr": float("nan"),
            "ci_low": float("nan"),
            "ci_high": float("nan"),
            "p_value": float("nan"),
        }
    mean = float(values.mean())
    stderr = float(values.std(ddof=1) / sqrt(n)) if n > 1 else float("nan")
    ci_low, ci_high = bootstrap_ci(values)
    return {
        "N": n,
        "mean": mean,
        "median": float(np.median(values)),
        "positive_rate": float((values > 0).mean()),
        "stderr": stderr,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "p_value": one_sample_pvalue(values),
    }


def era_means(events: pd.DataFrame, metric: str) -> Dict[str, float]:
    out = {}
    for era in ERAS:
        subset = events.loc[events.era == era, metric].astype(float)
        out[era] = float(subset.mean()) if len(subset) else float("nan")
    return out


def same_sign_across_eras(means: Dict[str, float]) -> bool:
    vals = [means[k] for k in ERAS if np.isfinite(means.get(k, np.nan))]
    if len(vals) < 3:
        return False
    return all(v > 0 for v in vals) or all(v < 0 for v in vals)


def positive_era_count(means: Dict[str, float]) -> int:
    return sum(1 for k in ERAS if np.isfinite(means.get(k, np.nan)) and means[k] > 0)


def classify_replicated(
    events: pd.DataFrame,
    metric: str,
    *,
    criteria: ReplicationCriteria = ReplicationCriteria(),
) -> Tuple[bool, List[str]]:
    reasons = []
    values = events[metric].astype(float)
    values = values[np.isfinite(values)]
    if len(values) < criteria.min_total_n:
        reasons.append("total_N_below_300")
        return False, reasons
    era_counts = {era: int((events.era == era).sum()) for era in ERAS}
    if any(era_counts[e] < criteria.min_era_n for e in ERAS):
        reasons.append("era_N_below_75")
        return False, reasons
    means = era_means(events, metric)
    if not same_sign_across_eras(means):
        reasons.append("not_same_sign")
        return False, reasons
    if positive_era_count(means) < criteria.min_positive_eras:
        reasons.append("insufficient_positive_eras")
        return False, reasons
    full_mean = float(values.mean())
    if abs(full_mean) < criteria.min_full_sample_atr:
        reasons.append("effect_too_small")
        return False, reasons
    era_contrib = []
    for era in ERAS:
        era_vals = events.loc[events.era == era, metric].astype(float)
        era_vals = era_vals[np.isfinite(era_vals)]
        era_contrib.append(float(era_vals.sum()))
    total_positive = sum(x for x in era_contrib if x > 0)
    if total_positive > 0 and max(era_contrib) / total_positive > criteria.max_era_contribution:
        reasons.append("single_era_dominance")
        return False, reasons
    return True, reasons


def build_edge_map(events: pd.DataFrame, *, horizon: int = 12, direction: str = "continuation") -> pd.DataFrame:
    metric = f"{direction}_atr_{horizon}"
    events = events.copy()
    events["displacement_quantile"] = assign_displacement_quantile(events)
    rows: List[Dict[str, Any]] = []
    group_cols = ["level", "event_type", "time_bucket", "displacement_quantile"]
    all_quantile = events.copy()
    all_quantile["displacement_quantile"] = "ALL"
    combined = pd.concat([events, all_quantile], ignore_index=True)
    for (level, event_type, time_bucket, quantile), group in combined.groupby(
        group_cols, sort=False
    ):
        if group.empty:
            continue
        summary = summarize_group(group[metric].to_numpy())
        means = era_means(group, metric)
        mfe = summarize_group(group[f"mfe_atr_{horizon}"].to_numpy())
        mae = summarize_group(group[f"mae_atr_{horizon}"].to_numpy())
        replicated, _ = classify_replicated(group, metric)
        rows.append(
            {
                "level": level,
                "event_type": event_type,
                "direction": direction,
                "time_bucket": time_bucket,
                "displacement_quantile": quantile,
                "horizon": horizon,
                "N": summary["N"],
                "sample_tier": sample_tier(summary["N"]),
                "mean_forward_atr": summary["mean"],
                "median_forward_atr": summary["median"],
                "positive_return_rate": summary["positive_rate"],
                "mfe_atr": mfe["mean"],
                "mae_atr": mae["mean"],
                "effect_size": summary["mean"],
                "standard_error": summary["stderr"],
                "ci95_low": summary["ci_low"],
                "ci95_high": summary["ci_high"],
                "raw_p_value": summary["p_value"],
                "era1_avg_atr": means["era1"],
                "era2_avg_atr": means["era2"],
                "era3_avg_atr": means["era3"],
                "same_sign_across_eras": same_sign_across_eras(means),
                "replicated": replicated,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame["fdr_q_value"] = []
        frame["fdr_survivor_5pct"] = []
        return frame
    adjusted = benjamini_hochberg(frame["raw_p_value"].fillna(1.0).tolist())
    frame["fdr_q_value"] = adjusted
    frame["fdr_survivor_5pct"] = frame["fdr_q_value"] <= 0.05
    return frame


def build_multiple_testing(edge_map: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "level",
        "event_type",
        "direction",
        "time_bucket",
        "displacement_quantile",
        "horizon",
        "N",
        "mean_forward_atr",
        "raw_p_value",
        "fdr_q_value",
        "fdr_survivor_5pct",
        "replicated",
    ]
    return edge_map[cols].sort_values(["fdr_q_value", "N"], ascending=[True, False])


def build_era_replication(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        for direction in ("continuation", "reversal"):
            metric = f"{direction}_atr_{horizon}"
            for (level, event_type), group in events.groupby(["level", "event_type"], sort=False):
                means = era_means(group, metric)
                replicated, reasons = classify_replicated(group, metric)
                rows.append(
                    {
                        "level": level,
                        "event_type": event_type,
                        "direction": direction,
                        "horizon": horizon,
                        "N": len(group),
                        "full_mean_atr": float(group[metric].astype(float).mean()),
                        "era1_mean_atr": means["era1"],
                        "era2_mean_atr": means["era2"],
                        "era3_mean_atr": means["era3"],
                        "same_sign_across_eras": same_sign_across_eras(means),
                        "replicated": replicated,
                        "failure_reasons": ";".join(reasons) if reasons else "",
                    }
                )
    return pd.DataFrame(rows)


def build_level_comparison(edge_map: pd.DataFrame) -> pd.DataFrame:
    subset = edge_map.loc[
        (edge_map.horizon == 12)
        & (edge_map.direction == "continuation")
        & (edge_map.displacement_quantile == "ALL")
    ].copy()
    if subset.empty:
        return subset
    return (
        subset.groupby(["level", "event_type"], as_index=False)
        .agg(
            N=("N", "sum"),
            mean_forward_atr=("mean_forward_atr", "mean"),
            era1_avg_atr=("era1_avg_atr", "mean"),
            era2_avg_atr=("era2_avg_atr", "mean"),
            era3_avg_atr=("era3_avg_atr", "mean"),
            replicated_rows=("replicated", "sum"),
        )
        .sort_values("mean_forward_atr", ascending=False)
    )


def build_time_bucket_comparison(edge_map: pd.DataFrame) -> pd.DataFrame:
    subset = edge_map.loc[(edge_map.horizon == 12) & (edge_map.direction == "continuation")].copy()
    return (
        subset.groupby(["time_bucket", "level", "event_type"], as_index=False)
        .agg(N=("N", "sum"), mean_forward_atr=("mean_forward_atr", "mean"), replicated=("replicated", "max"))
        .sort_values(["time_bucket", "mean_forward_atr"], ascending=[True, False])
    )


def build_displacement_monotonicity(events: pd.DataFrame, *, horizon: int = 12) -> pd.DataFrame:
    rows = []
    metric = f"continuation_atr_{horizon}"
    events = events.copy()
    events["displacement_quantile"] = assign_displacement_quantile(events, "body_atr")
    for (level, event_type), group in events.groupby(["level", "event_type"], sort=False):
        means = []
        for label in ["Q1", "Q2", "Q3", "Q4"]:
            bucket = group.loc[group.displacement_quantile == label, metric].astype(float)
            bucket = bucket[np.isfinite(bucket)]
            means.append(float(bucket.mean()) if len(bucket) else float("nan"))
        monotonic_up = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] <= means[i + 1] for i in range(3))
        monotonic_down = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] >= means[i + 1] for i in range(3))
        rows.append(
            {
                "level": level,
                "event_type": event_type,
                "horizon": horizon,
                "Q1_mean": means[0],
                "Q2_mean": means[1],
                "Q3_mean": means[2],
                "Q4_mean": means[3],
                "monotonic_increasing": monotonic_up,
                "monotonic_decreasing": monotonic_down,
            }
        )
    return pd.DataFrame(rows)


def build_regime_diagnostics(events: pd.DataFrame, *, horizon: int = 12) -> pd.DataFrame:
    metric = f"continuation_atr_{horizon}"
    rows = []
    for regime_col in ["htf_vol_regime", "above_prior_rth_close", "overnight_gap_direction"]:
        for (level, event_type, regime_val), group in events.groupby(
            ["level", "event_type", regime_col], sort=False
        ):
            vals = group[metric].astype(float)
            vals = vals[np.isfinite(vals)]
            if len(vals) < 75:
                continue
            rows.append(
                {
                    "level": level,
                    "event_type": event_type,
                    "regime_dimension": regime_col,
                    "regime_value": regime_val,
                    "N": len(vals),
                    "mean_forward_atr": float(vals.mean()),
                    "era1_mean": float(group.loc[group.era == "era1", metric].mean()),
                    "era2_mean": float(group.loc[group.era == "era2", metric].mean()),
                    "era3_mean": float(group.loc[group.era == "era3", metric].mean()),
                }
            )
    return pd.DataFrame(rows)


def final_classification(edge_map: pd.DataFrame, era_replication: pd.DataFrame) -> str:
    primary_levels = {"PDH", "PDL", "ONH", "ONL", "ORH", "ORL"}
    primary = era_replication.loc[
        (era_replication.horizon == 12)
        & (era_replication.direction == "continuation")
        & (era_replication.level.isin(primary_levels))
        & (era_replication.replicated)
        & (era_replication.N >= 300)
        & (era_replication.full_mean_atr.abs() >= 0.05)
    ]
    strong = primary.loc[primary["full_mean_atr"].abs() >= 0.08]
    survivors = edge_map.loc[
        (edge_map.horizon == 12)
        & (edge_map.direction == "continuation")
        & (edge_map.level.isin(primary_levels))
        & (edge_map.displacement_quantile == "ALL")
        & (edge_map.replicated)
        & (edge_map.fdr_survivor_5pct)
        & (edge_map.N >= 300)
        & (edge_map.mean_forward_atr.abs() >= 0.05)
    ]
    if len(strong) >= 2 and len(survivors) >= 2:
        return "A"
    promising = primary.loc[primary["full_mean_atr"].abs() >= 0.03]
    if len(promising) >= 1 and len(survivors) >= 1:
        return "B"
    weak = era_replication.loc[
        (era_replication.horizon == 12)
        & (era_replication.level.isin(primary_levels))
        & (era_replication.same_sign_across_eras)
        & (era_replication.N >= 100)
        & (era_replication.full_mean_atr.abs() >= 0.02)
    ]
    if not weak.empty:
        return "C"
    return "D"


def run_session_liquidity_study(
    *,
    output: Path = RESULTS,
    config: FrozenConfig = FrozenConfig(),
    market: pd.DataFrame | None = None,
    events: pd.DataFrame | None = None,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    if market is None:
        market = load_unified_market_data(config)
    events_path = output / "session_liquidity_events.csv"
    if events is None:
        if events_path.exists():
            events = pd.read_csv(events_path)
        else:
            events = extract_session_liquidity_events(market, config)
            events.to_csv(events_path, index=False)
    elif not events_path.exists():
        events.to_csv(events_path, index=False)

    edge_parts = []
    for horizon in HORIZONS:
        for direction in ("continuation", "reversal"):
            edge_parts.append(build_edge_map(events, horizon=horizon, direction=direction))
    edge_map = pd.concat(edge_parts, ignore_index=True)
    edge_map.to_csv(output / "edge_map.csv", index=False)

    era_replication = build_era_replication(events)
    era_replication.to_csv(output / "era_replication.csv", index=False)
    level_comparison = build_level_comparison(edge_map)
    level_comparison.to_csv(output / "level_comparison.csv", index=False)
    time_bucket_comparison = build_time_bucket_comparison(edge_map)
    time_bucket_comparison.to_csv(output / "time_bucket_comparison.csv", index=False)
    displacement_monotonicity = build_displacement_monotonicity(events)
    displacement_monotonicity.to_csv(output / "displacement_monotonicity.csv", index=False)
    regime_diagnostics = build_regime_diagnostics(events)
    regime_diagnostics.to_csv(output / "regime_diagnostics.csv", index=False)
    multiple_testing = build_multiple_testing(edge_map)
    multiple_testing.to_csv(output / "multiple_testing.csv", index=False)

    classification = final_classification(edge_map, era_replication)
    fdr_survivors = int(edge_map["fdr_survivor_5pct"].sum())
    replicated_rows = edge_map.loc[edge_map.replicated].sort_values("mean_forward_atr", key=abs, ascending=False)
    primary_levels = {"PDH", "PDL", "ONH", "ONL", "ORH", "ORL"}
    top_rows = replicated_rows.loc[
        (replicated_rows.horizon == 12)
        & (replicated_rows.direction == "continuation")
        & (replicated_rows.level.isin(primary_levels))
        & (replicated_rows.displacement_quantile == "ALL")
    ].head(5)

    manifest = {
        "phase": "Strategy Research V2 — Session Liquidity Edge Discovery",
        "classification": classification,
        "data_range": {
            "start": str(market.index.min()),
            "end": str(market.index.max()),
            "bars_5m": len(market),
        },
        "eras": ERAS,
        "contaminated_windows": CONTAMINATED_WINDOWS,
        "discovery_label": "DEVELOPMENT / DISCOVERY — no period treated as OOS",
        "total_events": len(events),
        "events_by_era": events.groupby("era").size().to_dict(),
        "levels_tested": list(LEVELS),
        "event_types_tested": list(EVENT_TYPES),
        "fdr_survivors_5pct": fdr_survivors,
        "replicated_edge_rows": int(edge_map["replicated"].sum()),
        "lookahead_audit": True,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = [
        "# Session Liquidity Edge Discovery Report",
        "",
        f"**Classification:** {classification}",
        "",
        f"Data range: {manifest['data_range']['start']} → {manifest['data_range']['end']}",
        f"Total 5m bars: {manifest['data_range']['bars_5m']}",
        f"Total events: {len(events)}",
        f"FDR survivors (5%): {fdr_survivors}",
        f"Replicated edge-map rows: {int(edge_map['replicated'].sum())}",
        "",
        "## Contaminated windows (all discovery)",
    ]
    for window in CONTAMINATED_WINDOWS:
        report.append(f"- {window}")
    report.append("")
    report.append("## Top replicated candidates")
    for _, row in top_rows.iterrows():
        report.append(
            f"- {row.level} {row.event_type} {row.time_bucket} h{row.horizon} "
            f"N={row.N} mean={row.mean_forward_atr:.4f} "
            f"era1={row.era1_avg_atr:.4f} era2={row.era2_avg_atr:.4f} era3={row.era3_avg_atr:.4f}"
        )
    (output / "SESSION_LIQUIDITY_EDGE_REPORT.md").write_text("\n".join(report) + "\n")

    with pd.ExcelWriter(output / "SESSION_LIQUIDITY_EDGE.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("events_head", events.head(5000)),
            ("edge_map", edge_map),
            ("era_replication", era_replication),
            ("level_comparison", level_comparison),
            ("time_bucket", time_bucket_comparison),
            ("displacement", displacement_monotonicity),
            ("regime", regime_diagnostics),
            ("multiple_testing", multiple_testing),
        ):
            export = df.copy()
            for column in export.columns:
                if pd.api.types.is_datetime64_any_dtype(export[column]):
                    series = pd.to_datetime(export[column], errors="coerce")
                    if hasattr(series.dt, "tz") and series.dt.tz is not None:
                        export[column] = series.dt.tz_localize(None)
            export.to_excel(writer, sheet_name=name[:31], index=False)

    manifest["classification"] = classification
    manifest["top_replicated"] = replicated_rows.head(10).to_dict(orient="records")
    return manifest
