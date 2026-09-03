"""Analysis, edge maps, replication, and reporting for Phase 21."""

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
    CONTAMINATED_WINDOWS,
    DATA_PATHS,
    DirectionalReplication,
    ERAS,
    HORIZONS,
    MagnitudeReplication,
    RESULTS,
    SHOCK_PERCENTILE_BINS,
    VOL_MEASURES,
)
from .forward_returns import attach_forward_outcomes
from .volatility_events import assign_era, extract_volatility_events
from .volatility_measures import prepare_volatility_frame


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


def bootstrap_ci(values: np.ndarray, *, n: int = 1000, seed: int = 21) -> Tuple[float, float]:
    values = values.astype(float)
    values = values[np.isfinite(values)]
    if len(values) < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = [float(np.mean(rng.choice(values, size=len(values), replace=True))) for _ in range(n)]
    return float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def compute_unconditional_baselines(data: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    frame = data.copy()
    tz = config.exchange_timezone
    in_window = []
    for ts in frame.index:
        era = assign_era(ts, tz)
        in_window.append(era != "outside")
    frame = frame.loc[in_window]
    rows = []
    for horizon in HORIZONS:
        signed = (frame["close"].shift(-horizon) - frame["close"]) / frame["atr_24"]
        abs_ret = signed.abs()
        valid = signed[np.isfinite(signed)]
        abs_valid = abs_ret[np.isfinite(abs_ret)]
        cum_tr = frame["true_range"].rolling(horizon).sum().shift(-horizon) / frame["atr_24"]
        future_rv = frame["returns"].rolling(horizon).std().shift(-horizon)
        rows.append(
            {
                "horizon": horizon,
                "minutes_approx": horizon * 5,
                "N": int(len(valid)),
                "mean_signed_return_atr": float(valid.mean()),
                "mean_abs_return_atr": float(abs_valid.mean()),
                "median_abs_return_atr": float(abs_valid.median()),
                "mean_future_rv": float(future_rv[np.isfinite(future_rv)].mean()),
                "mean_cumulative_tr_atr": float(cum_tr[np.isfinite(cum_tr)].mean()),
            }
        )
    return pd.DataFrame(rows)


def era_means(events: pd.DataFrame, metric: str) -> Dict[str, float]:
    out = {}
    for era in ERAS:
        subset = events.loc[events.era == era, metric].astype(float)
        subset = subset[np.isfinite(subset)]
        out[era] = float(subset.mean()) if len(subset) else float("nan")
    return out


def same_sign(means: Dict[str, float]) -> bool:
    vals = [means[k] for k in ERAS if np.isfinite(means.get(k, np.nan))]
    if len(vals) < 3:
        return False
    return all(v > 0 for v in vals) or all(v < 0 for v in vals)


def classify_directional(events: pd.DataFrame, metric: str, criteria: DirectionalReplication = DirectionalReplication()) -> bool:
    values = events[metric].astype(float)
    values = values[np.isfinite(values)]
    if len(values) < criteria.min_total_n:
        return False
    if any((events.era == era).sum() < criteria.min_era_n for era in ERAS):
        return False
    means = era_means(events, metric)
    if not same_sign(means):
        return False
    if sum(1 for k in ERAS if np.isfinite(means[k]) and means[k] > 0) < criteria.min_positive_eras:
        return False
    if abs(float(values.mean())) < criteria.min_effect_atr:
        return False
    era_contrib = [float(events.loc[events.era == era, metric].astype(float).sum()) for era in ERAS]
    pos_total = sum(x for x in era_contrib if x > 0)
    if pos_total > 0 and max(era_contrib) / pos_total > criteria.max_era_contribution:
        return False
    return True


def classify_magnitude(
    events: pd.DataFrame,
    metric: str,
    baseline: float,
    criteria: MagnitudeReplication = MagnitudeReplication(),
) -> Tuple[bool, float]:
    values = events[metric].astype(float)
    values = values[np.isfinite(values)]
    if len(values) < criteria.min_total_n or not np.isfinite(baseline) or baseline <= 0:
        return False, float("nan")
    if any((events.era == era).sum() < criteria.min_era_n for era in ERAS):
        return False, float("nan")
    uplift = (float(values.mean()) / baseline - 1.0) * 100.0
    era_uplifts = []
    for era in ERAS:
        era_vals = events.loc[events.era == era, metric].astype(float)
        era_vals = era_vals[np.isfinite(era_vals)]
        era_uplifts.append(float(era_vals.mean()) / baseline - 1.0 if len(era_vals) else float("nan"))
    if not all(np.isfinite(x) and x > 0 for x in era_uplifts):
        return False, uplift
    if uplift < criteria.min_uplift_pct:
        return False, uplift
    return True, uplift


def build_edge_map(
    events: pd.DataFrame,
    *,
    family: str,
    metric: str,
    baseline_value: float,
    orientation: str = "continuation",
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    group_cols = [
        "event_family",
        "vol_measure",
        "transition",
        "compression_duration",
        "shock_percentile_bin",
        "transition_direction",
    ]
    for horizon in HORIZONS:
        col = metric if "{h}" not in metric else metric.format(h=horizon)
        if "{h}" in metric:
            col = metric.format(h=horizon)
        else:
            col = f"{metric}_{horizon}" if not metric.endswith(str(horizon)) else metric
        if family == "directional":
            col = f"{orientation}_atr_{horizon}"
        elif family == "magnitude":
            col = f"abs_return_atr_{horizon}"
        for keys, group in events.groupby(group_cols, dropna=False, sort=False):
            if group.empty:
                continue
            vals = group[col].astype(float)
            vals = vals[np.isfinite(vals)]
            if len(vals) == 0:
                continue
            means = era_means(group, col)
            mean_val = float(vals.mean())
            stderr = float(vals.std(ddof=1) / sqrt(len(vals))) if len(vals) > 1 else float("nan")
            ci_low, ci_high = bootstrap_ci(vals.to_numpy())
            if family == "magnitude":
                replicated, uplift = classify_magnitude(group, col, baseline_value)
            else:
                replicated = classify_directional(group, col)
                uplift = float("nan")
            rows.append(
                {
                    "event_family": keys[0],
                    "vol_measure": keys[1],
                    "transition": keys[2],
                    "compression_duration": keys[3],
                    "shock_percentile_bin": keys[4],
                    "transition_direction": keys[5],
                    "horizon": horizon,
                    "orientation": orientation if family == "directional" else "n/a",
                    "N": len(vals),
                    "sample_tier": sample_tier(len(vals)),
                    "mean_signed_return_atr": float(group[f"signed_return_atr_{horizon}"].astype(float).mean()),
                    "median_signed_return_atr": float(group[f"signed_return_atr_{horizon}"].astype(float).median()),
                    "positive_signed_rate": float((group[f"signed_return_atr_{horizon}"].astype(float) > 0).mean()),
                    "mean_abs_return_atr": float(group[f"abs_return_atr_{horizon}"].astype(float).mean()),
                    "median_abs_return_atr": float(group[f"abs_return_atr_{horizon}"].astype(float).median()),
                    "mfe_atr": float(group[f"mfe_atr_{horizon}"].astype(float).mean()),
                    "mae_atr": float(group[f"mae_atr_{horizon}"].astype(float).mean()),
                    "future_rv": float(group[f"future_rv_{horizon}"].astype(float).mean()),
                    "effect_value": mean_val,
                    "uplift_pct_vs_baseline": uplift,
                    "standard_error": stderr,
                    "ci95_low": ci_low,
                    "ci95_high": ci_high,
                    "era1": means["era1"],
                    "era2": means["era2"],
                    "era3": means["era3"],
                    "same_sign_across_eras": same_sign(means),
                    "replicated": replicated,
                    "raw_p_value": one_sample_pvalue(vals.to_numpy()) if family == "directional" else one_sample_pvalue(vals.to_numpy()),
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


def build_era_replication(events: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        baseline_abs = float(baselines.loc[baselines.horizon == horizon, "mean_abs_return_atr"].iloc[0])
        for (family, vol, transition), group in events.groupby(["event_family", "vol_measure", "transition"]):
            for orientation in ("continuation", "reversal"):
                col = f"{orientation}_atr_{horizon}"
                means = era_means(group, col)
                rows.append(
                    {
                        "event_family": family,
                        "vol_measure": vol,
                        "transition": transition,
                        "orientation": orientation,
                        "horizon": horizon,
                        "N": len(group),
                        "mean_directional_atr": float(group[col].astype(float).mean()),
                        "era1": means["era1"],
                        "era2": means["era2"],
                        "era3": means["era3"],
                        "directional_replicated": classify_directional(group, col),
                    }
                )
            abs_col = f"abs_return_atr_{horizon}"
            means = era_means(group, abs_col)
            rep_mag, uplift = classify_magnitude(group, abs_col, baseline_abs)
            rows.append(
                {
                    "event_family": family,
                    "vol_measure": vol,
                    "transition": transition,
                    "orientation": "magnitude",
                    "horizon": horizon,
                    "N": len(group),
                    "mean_directional_atr": float(group[abs_col].astype(float).mean()),
                    "uplift_pct": uplift,
                    "era1": means["era1"],
                    "era2": means["era2"],
                    "era3": means["era3"],
                    "directional_replicated": rep_mag,
                }
            )
    return pd.DataFrame(rows)


def build_monotonicity(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    shocks = events.loc[events.event_family == "VOLATILITY_SHOCK"]
    for horizon in HORIZONS:
        col = f"abs_return_atr_{horizon}"
        means = []
        for bucket in SHOCK_PERCENTILE_BINS:
            bucket_vals = shocks.loc[shocks.shock_percentile_bin == bucket, col].astype(float)
            bucket_vals = bucket_vals[np.isfinite(bucket_vals)]
            means.append(float(bucket_vals.mean()) if len(bucket_vals) else float("nan"))
        mono = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] <= means[i + 1] for i in range(4))
        rows.append({"analysis": "shock_extremeness", "horizon": horizon, **{f"bin_{i}": means[i] for i in range(5)}, "monotonic_increasing": mono})
    comp = events.loc[events.event_family == "COMPRESSION_EXPANSION"]
    for horizon in HORIZONS:
        col = f"abs_return_atr_{horizon}"
        duration_order = ["1-3", "4-6", "7-12", "13-24", "25+"]
        means = []
        for bucket in duration_order:
            vals = comp.loc[comp.compression_duration == bucket, col].astype(float)
            vals = vals[np.isfinite(vals)]
            means.append(float(vals.mean()) if len(vals) else float("nan"))
        mono = all(np.isfinite(means[i]) and np.isfinite(means[i + 1]) and means[i] <= means[i + 1] for i in range(4))
        rows.append({"analysis": "compression_duration", "horizon": horizon, **{f"dur_{i}": means[i] for i in range(5)}, "monotonic_increasing": mono})
    return pd.DataFrame(rows)


def build_session_control(events: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for horizon in HORIZONS:
        col = f"abs_return_atr_{horizon}"
        for bucket in events["time_bucket"].dropna().unique():
            event_group = events.loc[events.time_bucket == bucket]
            bar_group = data.loc[data.time_bucket == bucket]
            if len(event_group) < 100 or len(bar_group) < 100:
                continue
            base_vals = ((bar_group["close"].shift(-horizon) - bar_group["close"]) / bar_group["atr_24"]).abs()
            base_vals = base_vals[np.isfinite(base_vals)]
            event_mean = float(event_group[col].astype(float).mean())
            base_mean = float(base_vals.mean()) if len(base_vals) else float("nan")
            rows.append(
                {
                    "time_bucket": bucket,
                    "horizon": horizon,
                    "event_N": len(event_group),
                    "event_mean_abs_atr": event_mean,
                    "unconditional_bucket_abs_atr": base_mean,
                    "uplift_pct": (event_mean / base_mean - 1.0) * 100.0 if base_mean > 0 else float("nan"),
                }
            )
    return pd.DataFrame(rows)


def classify_study(directional_map: pd.DataFrame, magnitude_map: pd.DataFrame) -> Dict[str, str]:
    dir_rep = directional_map.loc[
        directional_map.replicated
        & (directional_map.N >= 300)
        & (directional_map.fdr_survivor_5pct)
        & (directional_map["effect_value"].abs() >= 0.05)
    ]
    mag_rep = magnitude_map.loc[
        magnitude_map.replicated
        & (magnitude_map.N >= 300)
        & (magnitude_map.fdr_survivor_5pct)
        & (magnitude_map["uplift_pct_vs_baseline"] >= 10.0)
    ]

    def bucket(count: int, strong: int) -> str:
        if strong >= 2:
            return "A"
        if count >= 2:
            return "B"
        if count >= 1:
            return "C"
        return "D"

    directional = bucket(len(dir_rep), len(dir_rep))
    magnitude = bucket(len(mag_rep), len(mag_rep))
    overall_vals = [directional, magnitude]
    if "D" in overall_vals and "A" not in overall_vals:
        overall = "D" if overall_vals.count("D") == 2 else "C"
    elif "A" in overall_vals:
        overall = "B"
    else:
        overall = max(overall_vals, key=lambda x: "ABCD".index(x))
    return {"directional": directional, "magnitude": magnitude, "overall": overall}


def run_volatility_state_study(*, output: Path = RESULTS, config: FrozenConfig = FrozenConfig()) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_unified_market_data(config)
    data = prepare_volatility_frame(market, config)
    baselines = compute_unconditional_baselines(data, config)
    baselines.to_csv(output / "unconditional_baselines.csv", index=False)

    events = extract_volatility_events(market, config, prepared=data)
    events.to_csv(output / "volatility_state_events.csv", index=False)

    baseline_h12 = float(baselines.loc[baselines.horizon == 12, "mean_abs_return_atr"].iloc[0])
    magnitude_map = build_edge_map(events, family="magnitude", metric="abs_return_atr", baseline_value=baseline_h12)
    directional_map = build_edge_map(
        events, family="directional", metric="continuation_atr", baseline_value=baseline_h12, orientation="continuation"
    )
    magnitude_map.to_csv(output / "magnitude_edge_map.csv", index=False)
    directional_map.to_csv(output / "directional_edge_map.csv", index=False)

    era_replication = build_era_replication(events, baselines)
    era_replication.to_csv(output / "era_replication.csv", index=False)

    compression = events.loc[events.event_family.isin(["COMPRESSION", "COMPRESSION_EXPANSION"])]
    shock = events.loc[events.event_family == "VOLATILITY_SHOCK"]
    regime = events.loc[events.event_family == "REGIME_TRANSITION"]
    compression.to_csv(output / "compression_analysis.csv", index=False)
    shock.to_csv(output / "shock_analysis.csv", index=False)
    regime.to_csv(output / "regime_transition_analysis.csv", index=False)

    monotonicity = build_monotonicity(events)
    monotonicity.to_csv(output / "monotonicity.csv", index=False)

    events["year"] = pd.to_datetime(events["timestamp"]).dt.year
    time_stability = (
        events.groupby(["event_family", "year"])["abs_return_atr_12"].mean().reset_index()
    )
    time_stability.to_csv(output / "time_stability.csv", index=False)

    session_control = build_session_control(events, data)
    session_control.to_csv(output / "session_control.csv", index=False)

    multiple_testing_directional = directional_map[
        ["event_family", "vol_measure", "transition", "horizon", "N", "effect_value", "raw_p_value", "fdr_q_value", "fdr_survivor_5pct", "replicated"]
    ]
    multiple_testing_magnitude = magnitude_map[
        ["event_family", "vol_measure", "transition", "horizon", "N", "effect_value", "uplift_pct_vs_baseline", "raw_p_value", "fdr_q_value", "fdr_survivor_5pct", "replicated"]
    ]
    multiple_testing_directional.to_csv(output / "multiple_testing_directional.csv", index=False)
    multiple_testing_magnitude.to_csv(output / "multiple_testing_magnitude.csv", index=False)

    classes = classify_study(directional_map, magnitude_map)

    manifest = {
        "phase": "Strategy Research V3 — Volatility-State Transition Edge Discovery",
        "data_range": {"start": str(market.index.min()), "end": str(market.index.max()), "bars_5m": len(market)},
        "eras": ERAS,
        "contaminated_windows": CONTAMINATED_WINDOWS,
        "total_events": len(events),
        "transition_events": int(len(events)),
        "shock_events": int((events.event_family == "VOLATILITY_SHOCK").sum()),
        "events_by_era": events.groupby("era").size().to_dict(),
        "unconditional_baselines": baselines.to_dict(orient="records"),
        "fdr_survivors_directional": int(directional_map.fdr_survivor_5pct.sum()),
        "fdr_survivors_magnitude": int(magnitude_map.fdr_survivor_5pct.sum()),
        "classifications": classes,
        "lookahead_audit": True,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = [
        "# Volatility State Edge Discovery Report",
        "",
        f"Overall classification: **{classes['overall']}**",
        f"Directional: **{classes['directional']}** | Magnitude: **{classes['magnitude']}**",
        "",
        f"Bars: {len(market):,} | Events: {len(events):,}",
        f"Shock events: {(events.event_family == 'VOLATILITY_SHOCK').sum():,}",
        "",
        "## Unconditional baselines (abs return ATR)",
    ]
    for _, row in baselines.iterrows():
        report.append(f"- {row.minutes_approx}m: {row.mean_abs_return_atr:.4f}")
    (output / "VOLATILITY_STATE_EDGE_REPORT.md").write_text("\n".join(report) + "\n")

    with pd.ExcelWriter(output / "VOLATILITY_STATE_EDGE.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("baselines", baselines),
            ("events_head", events.head(5000)),
            ("magnitude_map", magnitude_map),
            ("directional_map", directional_map),
            ("era_replication", era_replication),
            ("monotonicity", monotonicity),
            ("session_control", session_control),
        ):
            export = df.copy()
            for column in export.columns:
                if pd.api.types.is_datetime64_any_dtype(export[column]):
                    series = pd.to_datetime(export[column], errors="coerce")
                    if hasattr(series.dt, "tz") and series.dt.tz is not None:
                        export[column] = series.dt.tz_localize(None)
            export.to_excel(writer, sheet_name=name[:31], index=False)

    manifest["top_magnitude"] = (
        magnitude_map.loc[magnitude_map.replicated].sort_values("uplift_pct_vs_baseline", ascending=False).head(5).to_dict(orient="records")
    )
    manifest["top_directional"] = (
        directional_map.loc[directional_map.replicated].sort_values("effect_value", key=abs, ascending=False).head(5).to_dict(orient="records")
    )
    return manifest
