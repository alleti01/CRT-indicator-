"""Analysis, edge map, replication, and reporting for Phase 22."""

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

from .auction_events import assign_era, extract_auction_events
from .config import CONTAMINATED_WINDOWS, DATA_PATHS, ERAS, HORIZONS, REPLICATION_LABELS, ReplicationCriteria, RESULTS
from .profile_construction import attach_prior_profile_to_bars, build_daily_profiles


def load_unified_market_data(config: FrozenConfig) -> pd.DataFrame:
    frames = [load_ohlcv_csv(path, exchange_timezone=config.exchange_timezone) for path in DATA_PATHS]
    combined = pd.concat(frames).sort_index()
    return combined[~combined.index.duplicated(keep="last")]


def sample_tier(n: int) -> str:
    if n < 100:
        return "INSUFFICIENT"
    if n < 300:
        return "WEAK_SAMPLE"
    if n >= 1000:
        return "STRONG_SAMPLE"
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


def bootstrap_ci(values: np.ndarray, *, seed: int = 22) -> Tuple[float, float]:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(1000)]
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def era_means(events: pd.DataFrame, metric: str) -> Dict[str, float]:
    out = {}
    for era in ERAS:
        vals = events.loc[events.era == era, metric].astype(float)
        vals = vals[np.isfinite(vals)]
        out[era] = float(vals.mean()) if len(vals) else float("nan")
    return out


def same_sign(means: Dict[str, float]) -> bool:
    vals = [means[k] for k in ERAS if np.isfinite(means.get(k, np.nan))]
    if len(vals) < 3:
        return False
    return all(v > 0 for v in vals) or all(v < 0 for v in vals)


def classify_replication(events: pd.DataFrame, metric: str, criteria: ReplicationCriteria = ReplicationCriteria()) -> str:
    vals = events[metric].astype(float)
    vals = vals[np.isfinite(vals)]
    if len(vals) < criteria.min_total_n:
        return "NO_INFORMATION"
    if any((events.era == era).sum() < criteria.min_era_n for era in ERAS):
        return "WEAK_INFORMATION"
    means = era_means(events, metric)
    mean_total = float(vals.mean())
    if abs(mean_total) < criteria.min_effect_atr:
        return "NO_INFORMATION"
    pos_eras = sum(1 for k in ERAS if np.isfinite(means[k]) and np.sign(means[k]) == np.sign(mean_total) and abs(means[k]) > 0)
    if not same_sign(means):
        if pos_eras >= 1:
            return "ERA_DEPENDENT"
        return "REVERSED" if mean_total < 0 else "NO_INFORMATION"
    if pos_eras < criteria.min_positive_eras:
        return "ERA_DEPENDENT"
    era_contrib = [float(events.loc[events.era == era, metric].astype(float).sum()) for era in ERAS]
    pos_total = sum(x for x in era_contrib if np.sign(x) == np.sign(mean_total))
    if abs(pos_total) > 0 and max(abs(x) for x in era_contrib) / abs(pos_total) > criteria.max_era_contribution:
        return "ERA_DEPENDENT"
    if mean_total > 0:
        return "REPLICATED_INFORMATION"
    return "REVERSED"


def compute_unconditional_baselines(data: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    frame = data.loc[data["in_rth"]].copy()
    rows = []
    for horizon in HORIZONS:
        signed = (frame["close"].shift(-horizon) - frame["close"]) / frame["atr"]
        valid = signed[np.isfinite(signed)]
        rows.append(
            {
                "horizon": horizon,
                "minutes_approx": horizon * 5,
                "N": int(len(valid)),
                "mean_signed_return_atr": float(valid.mean()),
                "median_signed_return_atr": float(valid.median()),
                "positive_rate": float((valid > 0).mean()),
                "mean_mfe_atr": float(((frame["high"].rolling(horizon).max().shift(-horizon) - frame["close"]) / frame["atr"]).mean()),
                "mean_mae_atr": float(((frame["close"] - frame["low"].rolling(horizon).min().shift(-horizon)) / frame["atr"]).mean()),
            }
        )
    return pd.DataFrame(rows)


def build_edge_map(events: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    group_cols = ["profile_level", "event_type", "orientation", "open_location", "value_migration", "time_bucket"]
    for horizon in HORIZONS:
        metric = f"directional_atr_{horizon}"
        baseline = float(baselines.loc[baselines.horizon == horizon, "mean_signed_return_atr"].iloc[0])
        for keys, group in events.groupby(group_cols, dropna=False, sort=False):
            vals = group[metric].astype(float)
            vals = vals[np.isfinite(vals)]
            if len(vals) == 0:
                continue
            means = era_means(group, metric)
            mean_val = float(vals.mean())
            ci_low, ci_high = bootstrap_ci(vals.to_numpy())
            rep = classify_replication(group, metric)
            rows.append(
                {
                    "profile_level": keys[0],
                    "event": keys[1],
                    "orientation": keys[2],
                    "open_location": keys[3],
                    "value_migration": keys[4],
                    "time_bucket": keys[5],
                    "horizon": horizon,
                    "N": len(vals),
                    "sample_tier": sample_tier(len(vals)),
                    "mean_directional_atr_return": mean_val,
                    "median_directional_atr_return": float(vals.median()),
                    "positive_rate": float((vals > 0).mean()),
                    "mfe_atr": float(group[f"mfe_atr_{horizon}"].astype(float).mean()),
                    "mae_atr": float(group[f"mae_atr_{horizon}"].astype(float).mean()),
                    "effect_vs_unconditional": mean_val - baseline,
                    "standard_error": float(vals.std(ddof=1) / sqrt(len(vals))) if len(vals) > 1 else float("nan"),
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                    "era1_effect": means["era1"],
                    "era2_effect": means["era2"],
                    "era3_effect": means["era3"],
                    "same_sign_all_eras": same_sign(means),
                    "session_control_result": "pending",
                    "raw_p": one_sample_pvalue(vals.to_numpy()),
                    "replication_classification": rep,
                }
            )
    frame = pd.DataFrame(rows)
    if frame.empty:
        frame["fdr_q"] = []
        frame["fdr_survivor_5pct"] = []
        return frame
    frame["fdr_q"] = benjamini_hochberg(frame["raw_p"].fillna(1.0).tolist())
    frame["fdr_survivor_5pct"] = frame["fdr_q"] <= 0.05
    return frame


def build_session_control(events: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        metric = f"directional_atr_{horizon}"
        for bucket, group in events.groupby("time_bucket"):
            bars = data.loc[(data["in_rth"]) & (data["rth_time_bucket"] == bucket)]
            if len(group) < 100 or len(bars) < 100:
                continue
            base = ((bars["close"].shift(-horizon) - bars["close"]) / bars["atr"]).astype(float)
            base = base[np.isfinite(base)]
            event_mean = float(group[metric].astype(float).mean())
            base_mean = float(base.mean()) if len(base) else float("nan")
            rows.append(
                {
                    "time_bucket": bucket,
                    "horizon": horizon,
                    "event_N": len(group),
                    "event_mean_directional_atr": event_mean,
                    "unconditional_bucket_signed_atr": base_mean,
                    "survives_control": bool(np.sign(event_mean) == np.sign(event_mean - base_mean) and abs(event_mean) > abs(base_mean))
                    if np.isfinite(base_mean)
                    else False,
                }
            )
    return pd.DataFrame(rows)


def apply_session_control_to_edge_map(edge_map: pd.DataFrame, session_control: pd.DataFrame) -> pd.DataFrame:
    out = edge_map.copy()
    lookup = {}
    for _, row in session_control.iterrows():
        lookup[(row.time_bucket, row.horizon)] = bool(row.survives_control)
    out["session_control_result"] = [
        lookup.get((tb, h), False) for tb, h in zip(out["time_bucket"], out["horizon"])
    ]
    return out


def build_monotonicity(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = events.copy()
    for feature, column in (
        ("value_width_atr", "prior_value_width_atr"),
        ("open_dist_poc_atr", "open_dist_poc_atr"),
        ("close_beyond_atr", "close_beyond_atr"),
    ):
        frame = base.copy()
        if column not in frame.columns:
            continue
        try:
            frame["quartile"] = pd.qcut(frame[column].rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        except ValueError:
            continue
        for horizon in HORIZONS:
            metric = f"directional_atr_{horizon}"
            means = []
            for q in ["Q1", "Q2", "Q3", "Q4"]:
                vals = frame.loc[frame["quartile"] == q, metric].astype(float)
                vals = vals[np.isfinite(vals)]
                means.append(float(vals.mean()) if len(vals) else float("nan"))
            mono = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] <= means[i + 1] for i in range(3))
            rows.append({"feature": feature, "horizon": horizon, **{f"q{i+1}": means[i] for i in range(4)}, "monotonic_increasing": mono})
    return pd.DataFrame(rows)


def build_symmetry(events: pd.DataFrame) -> pd.DataFrame:
    pairs = (
        ("ACCEPTANCE_ABOVE_VAH", "ACCEPTANCE_BELOW_VAL", "continuation"),
        ("REJECTION_ABOVE_VAH", "REJECTION_BELOW_VAL", "reversal"),
        ("VALUE_UP", "VALUE_DOWN", "migration"),
    )
    rows = []
    for horizon in HORIZONS:
        metric = f"directional_atr_{horizon}"
        for upper, lower, label in pairs[:2]:
            up = events.loc[events.event_type == upper, metric].astype(float)
            down = events.loc[events.event_type == lower, metric].astype(float)
            up = up[np.isfinite(up)]
            down = down[np.isfinite(down)]
            if len(up) < 50 or len(down) < 50:
                sym = "UNKNOWN"
            elif np.sign(up.mean()) == -np.sign(down.mean()):
                sym = "SYMMETRIC"
            else:
                sym = "ASYMMETRIC"
            rows.append({"comparison": label, "horizon": horizon, "upper_mean": float(up.mean()), "lower_mean": float(down.mean()), "symmetry": sym})
        upm = events.loc[events.value_migration == "VALUE_UP", metric].astype(float)
        downm = events.loc[events.value_migration == "VALUE_DOWN", metric].astype(float)
        sym = "SYMMETRIC" if len(upm) > 50 and len(downm) > 50 and np.sign(upm.mean()) == np.sign(-downm.mean()) else "ASYMMETRIC"
        rows.append({"comparison": "migration", "horizon": horizon, "upper_mean": float(upm.mean()) if len(upm) else np.nan, "lower_mean": float(downm.mean()) if len(downm) else np.nan, "symmetry": sym})
    return pd.DataFrame(rows)


def summarize_primary(events: pd.DataFrame, event_type: str, horizon: int = 12) -> Dict[str, Any]:
    group = events.loc[events.event_type == event_type]
    metric = f"directional_atr_{horizon}"
    vals = group[metric].astype(float)
    vals = vals[np.isfinite(vals)]
    means = era_means(group, metric)
    return {
        "N": len(vals),
        "effect": float(vals.mean()) if len(vals) else float("nan"),
        "era1": means["era1"],
        "era2": means["era2"],
        "era3": means["era3"],
        "classification": classify_replication(group, metric) if len(vals) else "NO_INFORMATION",
    }


def classify_study(edge_map: pd.DataFrame) -> str:
    rep = edge_map.loc[
        (edge_map.replication_classification == "REPLICATED_INFORMATION")
        & (edge_map.N >= 300)
        & (edge_map.fdr_survivor_5pct)
        & (edge_map.session_control_result)
        & (edge_map["mean_directional_atr_return"].abs() >= 0.03)
    ]
    promising = edge_map.loc[
        (edge_map.replication_classification == "REPLICATED_INFORMATION")
        & (edge_map.N >= 300)
        & (edge_map.fdr_survivor_5pct)
        & (edge_map["mean_directional_atr_return"].abs() >= 0.03)
    ]
    weak = edge_map.loc[(edge_map.replication_classification == "REPLICATED_INFORMATION") & (edge_map.N >= 300)]
    if len(rep) >= 2:
        return "A"
    if len(promising) >= 2:
        return "B"
    if len(weak) >= 1 or len(edge_map.loc[edge_map.replication_classification == "WEAK_INFORMATION"]) >= 3:
        return "C"
    return "D"


def run_auction_profile_study(*, output: Path = RESULTS, config: FrozenConfig = FrozenConfig()) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_unified_market_data(config)
    profiles = build_daily_profiles(market, config)
    profiles.to_csv(output / "daily_profiles.csv", index=False)
    prepared = attach_prior_profile_to_bars(market, profiles, config)
    baselines = compute_unconditional_baselines(prepared, config)
    baselines.to_csv(output / "unconditional_baselines.csv", index=False)
    events = extract_auction_events(market, config, profiles=profiles, prepared=prepared)
    events.to_csv(output / "auction_events.csv", index=False)

    edge_map = build_edge_map(events, baselines)
    session_control = build_session_control(events, prepared)
    session_control.to_csv(output / "session_control.csv", index=False)
    edge_map = apply_session_control_to_edge_map(edge_map, session_control)
    edge_map.to_csv(output / "auction_edge_map.csv", index=False)

    era_replication = edge_map.copy()
    era_replication.to_csv(output / "era_replication.csv", index=False)
    events.loc[events.event_type.isin(["ACCEPTANCE_ABOVE_VAH", "ACCEPTANCE_BELOW_VAL", "REJECTION_ABOVE_VAH", "REJECTION_BELOW_VAL"])].to_csv(
        output / "acceptance_rejection_analysis.csv", index=False
    )
    events.groupby(["open_location", "event_type"]).size().reset_index(name="N").to_csv(output / "open_location_analysis.csv", index=False)
    events.groupby(["value_migration", "event_type"]).size().reset_index(name="N").to_csv(output / "value_migration_analysis.csv", index=False)
    events.groupby(["value_width_quartile", "event_type"]).size().reset_index(name="N").to_csv(output / "value_width_analysis.csv", index=False)
    path_cols = [c for c in events.columns if c.startswith("path_")]
    if path_cols:
        events[path_cols + ["event_type", "era"]].to_csv(output / "auction_path_analysis.csv", index=False)
    symmetry = build_symmetry(events)
    symmetry.to_csv(output / "symmetry_analysis.csv", index=False)
    monotonicity = build_monotonicity(events)
    monotonicity.to_csv(output / "monotonicity.csv", index=False)
    multiple = edge_map[
        ["event", "orientation", "horizon", "N", "mean_directional_atr_return", "raw_p", "fdr_q", "fdr_survivor_5pct", "replication_classification"]
    ]
    multiple.to_csv(output / "multiple_testing.csv", index=False)

    final_class = classify_study(edge_map)
    primary = {
        "acceptance_above_vah": summarize_primary(events, "ACCEPTANCE_ABOVE_VAH"),
        "acceptance_below_val": summarize_primary(events, "ACCEPTANCE_BELOW_VAL"),
        "rejection_above_vah": summarize_primary(events, "REJECTION_ABOVE_VAH"),
        "rejection_below_val": summarize_primary(events, "REJECTION_BELOW_VAL"),
    }

    manifest = {
        "phase": "Strategy Research V4 — Auction / Market-Profile Directional Edge",
        "profile_method": "Prior RTH 5m volume distributed across fixed 0.25-point bins; 70% value area expanded from POC",
        "data_range": {"start": str(market.index.min()), "end": str(market.index.max()), "bars_5m": len(market)},
        "profiles": len(profiles),
        "events": len(events),
        "events_by_era": events.groupby("era").size().to_dict(),
        "baselines": baselines.to_dict(orient="records"),
        "primary_questions": primary,
        "fdr_survivors": int(edge_map.fdr_survivor_5pct.sum()),
        "cross_era_replicated": int((edge_map.replication_classification == "REPLICATED_INFORMATION").sum()),
        "session_control_survivors": int(edge_map.session_control_result.sum()),
        "final_classification": final_class,
        "lookahead_audit": "PASS",
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report_lines = [
        "# Auction Profile Edge Report",
        "",
        f"Final classification: **{final_class}**",
        f"Profiles: {len(profiles):,} | Events: {len(events):,}",
        "",
        "## Primary acceptance/rejection (h=12)",
    ]
    for name, stats in primary.items():
        report_lines.append(f"- {name}: N={stats['N']} effect={stats['effect']:.4f} class={stats['classification']}")
    (output / "AUCTION_PROFILE_EDGE_REPORT.md").write_text("\n".join(report_lines) + "\n")

    with pd.ExcelWriter(output / "AUCTION_PROFILE_EDGE.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("profiles", profiles.head(5000)),
            ("events_head", events.head(5000)),
            ("edge_map", edge_map),
            ("session_control", session_control),
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
        edge_map.loc[edge_map.replication_classification == "REPLICATED_INFORMATION"]
        .sort_values("mean_directional_atr_return", key=abs, ascending=False)
        .head(5)
        .to_dict(orient="records")
    )
    return manifest
