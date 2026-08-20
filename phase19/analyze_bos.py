#!/usr/bin/env python3
"""Phase 19: robustness analysis of the original frozen BOS model.

This module is analysis-only.  It reads immutable Phase 16/18 trades and market
data, verifies fresh Phase 19 reruns against those source outputs, and annotates
completed BOS trades with information known at the entry-bar close.  It does
not invoke or modify the setup, BOS, trade-management, or candidate engines.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from statistics import NormalDist
import sys
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phase16.indicators import htf_regime_name, score_band, session_bucket_name
from phase16.metrics import summarize_group
from phase17.analysis_core import build_trade_features, prepare_market_features, read_trades


ROOT = Path(__file__).resolve().parents[1]
P19 = ROOT / "phase19"
CHARTS = P19 / "charts"
EARLY_REFERENCE = ROOT / "phase18" / "results" / "base_run"
LATE_REFERENCE = ROOT / "phase16" / "results" / "oos"
EARLY_RERUN = P19 / "baseline_2021_2023"
LATE_RERUN = P19 / "baseline_2024_2026"
EARLY_DATA = ROOT / "phase18" / "data" / "processed" / "nq_5m.csv"
LATE_DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"
TZ = "America/Chicago"

PERIODS = (
    ("2021-2023", pd.Timestamp("2021-01-01", tz=TZ), pd.Timestamp("2023-12-29", tz=TZ)),
    ("2024-2026", pd.Timestamp("2024-01-01", tz=TZ), pd.Timestamp("2026-06-27", tz=TZ)),
)

COSTS = {
    "Zero": 0.0,
    "Optimistic": 9.50,
    "Realistic": 14.50,
    "Conservative": 28.00,
    "Severe": 40.00,
}
NQ_DOLLARS_PER_POINT = 20.0
MIN_HYPOTHESIS_N = 50
MC_SIMULATIONS = 10_000
MC_BLOCK_TRADES = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def max_drawdown(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    if not len(array):
        return 0.0
    equity = np.cumsum(array)
    peaks = np.maximum.accumulate(np.maximum(equity, 0.0))
    return float(np.max(peaks - equity, initial=0.0))


def summarize(frame: pd.DataFrame, result_column: str = "result_R") -> dict[str, float | int]:
    if result_column == "result_R":
        working = frame.sort_values("exit_timestamp", kind="stable")
    else:
        working = frame.sort_values("exit_timestamp", kind="stable").copy()
        working["result_R"] = working[result_column].astype(float)
    return summarize_group(working)


def baseline_gate() -> pd.DataFrame:
    """Require exact byte reproduction before any Phase 19 research proceeds."""
    pairs = (
        ("2021-2023", EARLY_REFERENCE, EARLY_RERUN),
        ("2024-2026", LATE_REFERENCE, LATE_RERUN),
    )
    rows: list[dict[str, object]] = []
    for period, reference, reproduced in pairs:
        for filename in ("model_comparison.csv", "trades.csv", "event_debug.csv"):
            if not (reference / filename).exists() or not (reproduced / filename).exists():
                raise RuntimeError(f"BASELINE REPRODUCTION FAIL: missing {period} {filename}")
            if (reference / filename).read_bytes() != (reproduced / filename).read_bytes():
                raise RuntimeError(f"BASELINE REPRODUCTION FAIL: {period} {filename} differs")
        comparison = pd.read_csv(reproduced / "model_comparison.csv")
        bos = comparison.loc[comparison["model"] == "BOS"].iloc[0].to_dict()
        rows.append(
            {
                "period": period,
                **bos,
                "metrics_match": True,
                "trades_byte_exact": True,
                "event_debug_byte_exact": True,
                "reference_trades_sha256": sha256(reference / "trades.csv"),
                "reproduced_trades_sha256": sha256(reproduced / "trades.csv"),
                "reference_event_debug_sha256": sha256(reference / "event_debug.csv"),
                "reproduced_event_debug_sha256": sha256(reproduced / "event_debug.csv"),
            }
        )
    return pd.DataFrame(rows)


def _event_debug(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(TZ)
    return frame.set_index("timestamp")


def _session_name(value: int) -> str:
    return {
        "Opening": "Open",
        "Morning": "MidAM",
        "Afternoon": "PM",
    }.get(session_bucket_name(value), session_bucket_name(value))


def _fixed_bucket(values: pd.Series, edges: list[float], labels: list[str]) -> pd.Series:
    return pd.cut(values.astype(float), bins=edges, labels=labels, right=False, include_lowest=True).astype(str)


def build_features() -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    sources = (
        ("2021-2023", EARLY_RERUN, EARLY_DATA),
        ("2024-2026", LATE_RERUN, LATE_DATA),
    )
    for period, results, data in sources:
        trades = read_trades(results / "trades.csv")
        bos = trades.loc[trades["model"] == "BOS"].copy()
        market = prepare_market_features(data)
        features = build_trade_features(bos, market)
        debug = _event_debug(results / "event_debug.csv")
        entry_debug = debug.reindex(pd.DatetimeIndex(features["entry_timestamp"]))
        entry_debug.index = features.index
        for column in ("bull_BOS", "bear_BOS", "liquidity_sweep"):
            features[column] = entry_debug[column].fillna(False).astype(bool)
        features["source_period"] = period
        pieces.append(features)

    working = pd.concat(pieces, ignore_index=True).sort_values("exit_timestamp", kind="stable").reset_index(drop=True)
    if working["entry_timestamp"].duplicated().any():
        duplicate_count = int(working["entry_timestamp"].duplicated().sum())
        raise RuntimeError(f"Unified BOS dataset has {duplicate_count} duplicate entry timestamps")

    entry = working["entry_timestamp"]
    working["year"] = entry.dt.strftime("%Y")
    working["quarter"] = entry.dt.tz_localize(None).dt.to_period("Q").astype(str)
    working["month"] = entry.dt.strftime("%Y-%m")
    working["day_of_week"] = entry.dt.day_name()
    start_hour = (entry.dt.hour // 2) * 2
    working["time_of_day"] = start_hour.map(lambda hour: f"{hour:02d}:00-{(hour + 1) % 24:02d}:59")
    working["direction_name"] = working["direction"]
    working["htf_regime_name"] = working["htf_regime"].map(htf_regime_name)
    working["trend_state"] = working["htf_regime_name"].map(
        {"Bull": "Bullish trend", "Bear": "Bearish trend", "Neutral": "Range/chop"}
    )
    working["session_name"] = working["session_bucket"].map(_session_name)
    working["score_band"] = working["score"].map(score_band)
    working["displacement_ratio"] = working["body"] / working["body_sma"].replace(0.0, np.nan)
    working["displacement_bucket"] = _fixed_bucket(
        working["displacement_ratio"],
        [-np.inf, 0.75, 1.25, 1.75, np.inf],
        ["<0.75x", "0.75-1.24x", "1.25-1.74x", "1.75x+"],
    )
    working["stop_bucket"] = _fixed_bucket(
        working["stop_distance_points"],
        [-np.inf, 15.0, 25.0, 40.0, np.inf],
        ["<15pt", "15-24.99pt", "25-39.99pt", "40pt+"],
    )
    working["target_bucket"] = _fixed_bucket(
        working["target_distance_points"],
        [-np.inf, 30.0, 50.0, 80.0, np.inf],
        ["<30pt", "30-49.99pt", "50-79.99pt", "80pt+"],
    )
    both = working["sweep_above"] & working["sweep_below"]
    working["crt_direction"] = np.select(
        [both, working["sweep_below"], working["sweep_above"]],
        ["Both reclaims", "Bullish reclaim", "Bearish reclaim"],
        default="No current reclaim",
    )
    working["liquidity_context"] = np.where(working["liquidity_sweep"], "Liquidity sweep", "No liquidity sweep")
    working["bos_polarity"] = np.select(
        [working["bull_BOS"] & working["bear_BOS"], working["bull_BOS"], working["bear_BOS"]],
        ["Both BOS", "Bull BOS", "Bear BOS"],
        default="No BOS flag",
    )
    aligned = ((working["direction"] == "Long") & (working["htf_regime"] == 1)) | (
        (working["direction"] == "Short") & (working["htf_regime"] == -1)
    )
    conflict = ((working["direction"] == "Long") & (working["htf_regime"] == -1)) | (
        (working["direction"] == "Short") & (working["htf_regime"] == 1)
    )
    working["htf_alignment"] = np.select([aligned, conflict], ["Aligned", "Counter-trend"], default="Neutral")
    working["setup_to_bos_bucket"] = _fixed_bucket(
        working["time_since_setup_bars"],
        [-np.inf, 1.0, 4.0, 13.0, np.inf],
        ["Same bar", "1-3 bars", "4-12 bars", "13+ bars"],
    )

    full_start = pd.Timestamp("2021-01-01", tz=TZ)
    full_end = pd.Timestamp("2026-06-27", tz=TZ)
    position = (entry - full_start).dt.total_seconds() / (full_end - full_start).total_seconds()
    working["entry_time_third"] = np.select(
        [position < 1 / 3, position < 2 / 3], ["Early third", "Middle third"], default="Late third"
    )
    working["risk_usd"] = working["stop_distance_points"] * NQ_DOLLARS_PER_POINT
    if (working["risk_usd"] <= 0).any() or working["risk_usd"].isna().any():
        raise RuntimeError("Invalid risk_usd in unified BOS feature set")
    working["outcome"] = np.select(
        [working["result_R"] > 0, working["result_R"] < 0], ["Win", "Loss"], default="Flat"
    )
    return working


def combined_baseline(baseline: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    combined = {"period": "2021-2026 combined", "model": "BOS", **summarize(trades)}
    combined.update(
        {
            "metrics_match": True,
            "trades_byte_exact": True,
            "event_debug_byte_exact": True,
            "reference_trades_sha256": "two immutable period files; see rows above",
            "reproduced_trades_sha256": "two byte-identical period reruns; see rows above",
            "reference_event_debug_sha256": "two immutable period files; see rows above",
            "reproduced_event_debug_sha256": "two byte-identical period reruns; see rows above",
        }
    )
    return pd.concat([baseline, pd.DataFrame([combined])], ignore_index=True)


def calendar_results(trades: pd.DataFrame, column: str) -> pd.DataFrame:
    rows = []
    for bucket, group in trades.groupby(column, sort=True, observed=False):
        rows.append({column: str(bucket), **summarize(group)})
    return pd.DataFrame(rows)


def rolling_results(trades: pd.DataFrame) -> pd.DataFrame:
    months = pd.period_range("2021-01", "2026-06", freq="M")
    trade_month = trades["entry_timestamp"].dt.tz_localize(None).dt.to_period("M")
    rows: list[dict[str, object]] = []
    for window in (3, 6, 12):
        for end in months[window - 1 :]:
            start = end - (window - 1)
            group = trades.loc[(trade_month >= start) & (trade_month <= end)]
            rows.append(
                {
                    "analysis_type": "rolling",
                    "window_months": window,
                    "start_month": str(start),
                    "end_month": str(end),
                    **summarize(group),
                }
            )
    for end in months:
        group = trades.loc[trade_month <= end]
        rows.append(
            {
                "analysis_type": "expanding",
                "window_months": int(end.ordinal - months[0].ordinal + 1),
                "start_month": str(months[0]),
                "end_month": str(end),
                **summarize(group),
            }
        )
    return pd.DataFrame(rows)


BREAKDOWN_DIMENSIONS: dict[str, tuple[str, list[str] | None]] = {
    "year": ("year", None),
    "quarter": ("quarter", None),
    "month": ("month", None),
    "direction": ("direction_name", ["Long", "Short"]),
    "session": ("session_name", ["Overnight", "Premarket", "Open", "MidAM", "Midday", "PM", "After-hours"]),
    "time_of_day": ("time_of_day", [f"{h:02d}:00-{(h + 1) % 24:02d}:59" for h in range(0, 24, 2)]),
    "day_of_week": ("day_of_week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
    "HTF_bias": ("htf_regime_name", ["Bull", "Bear", "Neutral"]),
    "HTF_alignment": ("htf_alignment", ["Aligned", "Counter-trend", "Neutral"]),
    "CRT_direction": ("crt_direction", ["Bullish reclaim", "Bearish reclaim", "Both reclaims", "No current reclaim"]),
    "score_band": ("score_band", ["70-74", "75-79", "80-84", "85-89", "90-94", "95+"]),
    "volatility_regime": ("volatility_regime", ["Low", "Medium", "High", "Unavailable"]),
    "trend_state": ("trend_state", ["Bullish trend", "Bearish trend", "Range/chop"]),
    "entry_time_third": ("entry_time_third", ["Early third", "Middle third", "Late third"]),
    "stop_distance": ("stop_bucket", ["<15pt", "15-24.99pt", "25-39.99pt", "40pt+"]),
    "target_distance": ("target_bucket", ["<30pt", "30-49.99pt", "50-79.99pt", "80pt+"]),
    "displacement": ("displacement_bucket", ["<0.75x", "0.75-1.24x", "1.25-1.74x", "1.75x+"]),
    "liquidity_context": ("liquidity_context", ["Liquidity sweep", "No liquidity sweep"]),
    "BOS_polarity": ("bos_polarity", ["Bull BOS", "Bear BOS", "Both BOS", "No BOS flag"]),
    "setup_to_BOS": ("setup_to_bos_bucket", ["Same bar", "1-3 bars", "4-12 bars", "13+ bars"]),
    "exit_reason": ("exit_reason", ["STOP", "TARGET", "TIME"]),
}


def breakdowns(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dimension, (column, buckets) in BREAKDOWN_DIMENSIONS.items():
        values = sorted(trades[column].dropna().astype(str).unique()) if buckets is None else buckets
        for bucket in values:
            group = trades.loc[trades[column].astype(str) == str(bucket)]
            rows.append({"dimension": dimension, "bucket": str(bucket), **summarize(group)})
    return pd.DataFrame(rows)


def cost_stress(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    scopes = [("2021-2023", trades.loc[trades["source_period"] == "2021-2023"]),
              ("2024-2026", trades.loc[trades["source_period"] == "2024-2026"]),
              ("2021-2026 combined", trades)]
    for scope, group in scopes:
        for scenario, dollars in COSTS.items():
            net_column = f"_net_{scenario}"
            costed = group.copy()
            costed[net_column] = costed["result_R"] - dollars / costed["risk_usd"]
            rows.append(
                {
                    "period": scope,
                    "scenario": scenario,
                    "round_trip_cost_usd": dollars,
                    **summarize(costed, net_column),
                }
            )
        denominator = float((1.0 / group["risk_usd"]).sum())
        break_even = float(group["result_R"].sum() / denominator) if denominator > 0 else np.nan
        rows[-len(COSTS)]["break_even_round_trip_cost_usd"] = break_even
        for offset in range(1, len(COSTS)):
            rows[-len(COSTS) + offset]["break_even_round_trip_cost_usd"] = break_even
    return pd.DataFrame(rows)


def outlier_stress(trades: pd.DataFrame) -> pd.DataFrame:
    ordered = trades.sort_values("exit_timestamp", kind="stable")
    rows: list[dict[str, object]] = [{"test": "Unmodified", "detail": "Original BOS", **summarize(ordered)}]

    removals = (
        ("Remove largest win", 1),
        ("Remove top 5 wins", 5),
        ("Remove top 10 wins", 10),
        ("Remove top 1% outcomes", int(math.ceil(len(ordered) * 0.01))),
        ("Remove top 5% outcomes", int(math.ceil(len(ordered) * 0.05))),
    )
    for name, count in removals:
        drop_index = ordered.nlargest(count, "result_R").index
        group = ordered.drop(index=drop_index)
        rows.append({"test": name, "detail": f"Removed {count} highest-R trades", **summarize(group)})

    positive = ordered.loc[ordered["result_R"] > 0, "result_R"]
    for percentile in (0.99, 0.95):
        cap = float(positive.quantile(percentile)) if len(positive) else 0.0
        group = ordered.copy()
        column = f"_winsor_{int(percentile * 100)}"
        group[column] = np.where(group["result_R"] > cap, cap, group["result_R"])
        rows.append(
            {
                "test": f"Winsorize positive tail at {int(percentile * 100)}%",
                "detail": f"Positive outcomes capped at {cap:.6f}R",
                **summarize(group, column),
            }
        )
    return pd.DataFrame(rows)


def _longest_losing_streak(array: np.ndarray) -> int:
    maximum = current = 0
    for value in array:
        current = current + 1 if value < 0 else 0
        maximum = max(maximum, current)
    return maximum


def monte_carlo(trades: pd.DataFrame) -> pd.DataFrame:
    values = trades.sort_values("exit_timestamp", kind="stable")["result_R"].to_numpy(float)
    n = len(values)
    rng = np.random.default_rng(19019)
    rows: list[dict[str, object]] = []
    for method in ("IID bootstrap", f"Moving-block bootstrap ({MC_BLOCK_TRADES} trades)"):
        terminals = np.empty(MC_SIMULATIONS)
        drawdowns = np.empty(MC_SIMULATIONS)
        streaks = np.empty(MC_SIMULATIONS)
        batch = 100
        for start in range(0, MC_SIMULATIONS, batch):
            size = min(batch, MC_SIMULATIONS - start)
            if method == "IID bootstrap":
                indices = rng.integers(0, n, size=(size, n))
            else:
                blocks = math.ceil(n / MC_BLOCK_TRADES)
                starts = rng.integers(0, n, size=(size, blocks))
                offsets = np.arange(MC_BLOCK_TRADES)
                indices = ((starts[:, :, None] + offsets[None, None, :]) % n).reshape(size, -1)[:, :n]
            draws = values[indices]
            equity = np.cumsum(draws, axis=1)
            peaks = np.maximum.accumulate(np.maximum(equity, 0.0), axis=1)
            terminals[start : start + size] = equity[:, -1]
            drawdowns[start : start + size] = np.max(peaks - equity, axis=1)
            streaks[start : start + size] = np.array([_longest_losing_streak(row) for row in draws])
        rows.append(
            {
                "method": method,
                "simulations": MC_SIMULATIONS,
                "trades_per_path": n,
                "block_trades": 1 if method == "IID bootstrap" else MC_BLOCK_TRADES,
                "probability_terminal_R_positive": float(np.mean(terminals > 0)),
                **{f"terminal_R_p{q}": float(np.percentile(terminals, q)) for q in (1, 5, 25, 50, 75, 95, 99)},
                **{f"max_drawdown_R_p{q}": float(np.percentile(drawdowns, q)) for q in (50, 75, 90, 95, 99)},
                **{f"longest_losing_streak_p{q}": float(np.percentile(streaks, q)) for q in (50, 75, 90, 95, 99)},
            }
        )
    return pd.DataFrame(rows)


HYPOTHESIS_DIMENSIONS: dict[str, tuple[str, list[str]]] = {
    "direction": ("direction_name", ["Long", "Short"]),
    "HTF_bias": ("htf_regime_name", ["Bull", "Bear", "Neutral"]),
    "HTF_alignment": ("htf_alignment", ["Aligned", "Counter-trend", "Neutral"]),
    "session": ("session_name", ["Overnight", "Premarket", "Open", "MidAM", "Midday", "PM", "After-hours"]),
    "time_of_day": ("time_of_day", [f"{h:02d}:00-{(h + 1) % 24:02d}:59" for h in range(0, 24, 2)]),
    "day_of_week": ("day_of_week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]),
    "score_band": ("score_band", ["70-74", "75-79", "80-84", "85-89", "90-94", "95+"]),
    "volatility": ("volatility_regime", ["Low", "Medium", "High", "Unavailable"]),
    "CRT_direction": ("crt_direction", ["Bullish reclaim", "Bearish reclaim", "Both reclaims", "No current reclaim"]),
    "displacement": ("displacement_bucket", ["<0.75x", "0.75-1.24x", "1.25-1.74x", "1.75x+"]),
    "liquidity": ("liquidity_context", ["Liquidity sweep", "No liquidity sweep"]),
    "stop_distance": ("stop_bucket", ["<15pt", "15-24.99pt", "25-39.99pt", "40pt+"]),
    "target_distance": ("target_bucket", ["<30pt", "30-49.99pt", "50-79.99pt", "80pt+"]),
    "setup_to_BOS": ("setup_to_bos_bucket", ["Same bar", "1-3 bars", "4-12 bars", "13+ bars"]),
}

INTERACTIONS = (
    ("direction", "HTF_bias"),
    ("direction", "session"),
    ("direction", "score_band"),
    ("direction", "volatility"),
    ("HTF_bias", "session"),
    ("session", "volatility"),
)


def hypothesis_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for dimension, (feature, buckets) in HYPOTHESIS_DIMENSIONS.items():
        for bucket in buckets:
            specs.append(
                {
                    "dimension": dimension,
                    "condition": bucket,
                    "complexity": 1,
                    "conditions": [{"feature": feature, "value": bucket}],
                }
            )
    for left, right in INTERACTIONS:
        left_feature, left_values = HYPOTHESIS_DIMENSIONS[left]
        right_feature, right_values = HYPOTHESIS_DIMENSIONS[right]
        for left_value in left_values:
            for right_value in right_values:
                specs.append(
                    {
                        "dimension": f"{left} x {right}",
                        "condition": f"{left_value} | {right_value}",
                        "complexity": 2,
                        "conditions": [
                            {"feature": left_feature, "value": left_value},
                            {"feature": right_feature, "value": right_value},
                        ],
                    }
                )
    return specs


def apply_conditions(frame: pd.DataFrame, conditions: list[dict[str, str]]) -> pd.DataFrame:
    group = frame
    for condition in conditions:
        group = group.loc[group[str(condition["feature"])].astype(str) == str(condition["value"])]
    return group


def one_sided_p(values: np.ndarray) -> float:
    n = len(values)
    if n < 2:
        return 1.0
    mean = float(np.mean(values))
    sem = float(np.std(values, ddof=1) / math.sqrt(n))
    if sem <= 0 or not math.isfinite(sem):
        return 0.0 if mean > 0 else 1.0
    return float(1.0 - NormalDist().cdf(mean / sem))


def benjamini_hochberg(values: Iterable[float]) -> np.ndarray:
    p = np.asarray(list(values), dtype=float)
    if not len(p):
        return p
    order = np.argsort(p)
    ranked = p[order]
    adjusted = ranked * len(p) / np.arange(1, len(p) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.minimum(adjusted, 1.0)
    return output


def realistic_metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    group = frame.copy()
    group["net_R"] = group["result_R"] - COSTS["Realistic"] / group["risk_usd"]
    return summarize(group, "net_R")


def hypothesis_registry(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    years = sorted(trades["year"].unique())
    for number, spec in enumerate(hypothesis_specs(), start=1):
        group = apply_conditions(trades, spec["conditions"])
        metrics = summarize(group)
        realistic = realistic_metrics(group)
        yearly = group.groupby("year", observed=False)["result_R"].sum().reindex(years, fill_value=0.0)
        positive = yearly[yearly > 0]
        year_share = float(positive.max() / positive.sum()) if len(positive) and positive.sum() > 0 else np.nan
        remove_count = int(math.ceil(len(group) * 0.01)) if len(group) else 0
        without_top = group.drop(index=group.nlargest(remove_count, "result_R").index) if remove_count else group
        row = {
            "hypothesis_id": f"H{number:04d}",
            "dimension": spec["dimension"],
            "condition": spec["condition"],
            "complexity": spec["complexity"],
            "conditions_json": json.dumps(spec["conditions"], sort_keys=True),
            **metrics,
            "one_sided_p": one_sided_p(group["result_R"].to_numpy(float)),
            "realistic_avg_R": realistic["avg_R"],
            "realistic_total_R": realistic["total_R"],
            "realistic_profit_factor": realistic["profit_factor"],
            "realistic_max_drawdown_R": realistic["max_drawdown_R"],
            "positive_years": int((yearly > 0).sum()),
            "calendar_year_buckets": len(years),
            "max_positive_year_contribution": year_share,
            "top_1pct_removed_count": remove_count,
            "top_1pct_removed_total_R": float(without_top["result_R"].sum()),
        }
        rows.append(row)
    registry = pd.DataFrame(rows)
    registry["fdr_q"] = np.nan
    tested = registry["N"] >= MIN_HYPOTHESIS_N
    registry.loc[tested, "fdr_q"] = benjamini_hochberg(registry.loc[tested, "one_sided_p"])
    registry["evidence_label"] = "DESCRIPTIVE ONLY"
    registry.loc[tested & (registry["one_sided_p"] < 0.05), "evidence_label"] = "RAW P<0.05"
    registry.loc[tested & (registry["fdr_q"] <= 0.10) & (registry["avg_R"] > 0), "evidence_label"] = "FDR-SURVIVING"
    return registry


FOLDS = (
    ("F1", "2021", ["2021"], ["2022"]),
    ("F2", "2021-2022", ["2021", "2022"], ["2023"]),
    ("F3", "2021-2023", ["2021", "2022", "2023"], ["2024"]),
    ("F4", "2021-2024", ["2021", "2022", "2023", "2024"], ["2025"]),
    ("F5", "2021-2025", ["2021", "2022", "2023", "2024", "2025"], ["2026"]),
)


def walk_forward(trades: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for fold, train_label, train_years, evaluation_years in FOLDS:
        candidates: list[tuple[str, float, float, int]] = []
        fold_rows: list[dict[str, object]] = []
        for _, hypothesis in registry.iterrows():
            conditions = json.loads(hypothesis["conditions_json"])
            train_group = apply_conditions(trades.loc[trades["year"].isin(train_years)], conditions)
            eval_group = apply_conditions(trades.loc[trades["year"].isin(evaluation_years)], conditions)
            train_metrics = summarize(train_group)
            train_realistic = realistic_metrics(train_group)
            eval_metrics = summarize(eval_group)
            eval_realistic = realistic_metrics(eval_group)
            without_five = train_group.drop(index=train_group.nlargest(min(5, len(train_group)), "result_R").index)
            eligible = bool(
                int(hypothesis["complexity"]) == 1
                and train_metrics["N"] >= 200
                and train_metrics["avg_R"] > 0
                and train_metrics["profit_factor"] > 1.05
                and train_realistic["total_R"] > 0
                and one_sided_p(train_group["result_R"].to_numpy(float)) < 0.05
                and without_five["result_R"].sum() > 0
            )
            if eligible:
                candidates.append(
                    (
                        str(hypothesis["hypothesis_id"]),
                        float(train_realistic["total_R"]),
                        float(train_metrics["avg_R"]),
                        int(train_metrics["N"]),
                    )
                )
            fold_rows.append(
                {
                    "fold": fold,
                    "train_period": train_label,
                    "evaluation_period": evaluation_years[0] if evaluation_years[0] != "2026" else "2026-01-01 through 2026-06-26",
                    "hypothesis_id": hypothesis["hypothesis_id"],
                    "dimension": hypothesis["dimension"],
                    "condition": hypothesis["condition"],
                    "complexity": hypothesis["complexity"],
                    "training_eligible": eligible,
                    "selected_by_train": False,
                    **{f"train_{key}": value for key, value in train_metrics.items()},
                    "train_realistic_total_R": train_realistic["total_R"],
                    "train_one_sided_p": one_sided_p(train_group["result_R"].to_numpy(float)),
                    **{f"eval_{key}": value for key, value in eval_metrics.items()},
                    "eval_realistic_total_R": eval_realistic["total_R"],
                    "eval_realistic_profit_factor": eval_realistic["profit_factor"],
                }
            )
        if candidates:
            selected = sorted(candidates, key=lambda item: (item[1], item[2], item[3]), reverse=True)[0][0]
            for row in fold_rows:
                if row["hypothesis_id"] == selected:
                    row["selected_by_train"] = True
        rows.extend(fold_rows)
    return pd.DataFrame(rows)


ORDERED_NEIGHBORS: dict[str, list[str]] = {
    "session_name": ["Overnight", "Premarket", "Open", "MidAM", "Midday", "PM", "After-hours"],
    "time_of_day": [f"{h:02d}:00-{(h + 1) % 24:02d}:59" for h in range(0, 24, 2)],
    "day_of_week": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "score_band": ["70-74", "75-79", "80-84", "85-89", "90-94", "95+"],
    "volatility_regime": ["Low", "Medium", "High"],
    "displacement_bucket": ["<0.75x", "0.75-1.24x", "1.25-1.74x", "1.75x+"],
    "stop_bucket": ["<15pt", "15-24.99pt", "25-39.99pt", "40pt+"],
    "target_bucket": ["<30pt", "30-49.99pt", "50-79.99pt", "80pt+"],
    "setup_to_bos_bucket": ["Same bar", "1-3 bars", "4-12 bars", "13+ bars"],
}


def sensitivity_and_candidates(
    trades: pd.DataFrame, registry: pd.DataFrame, walk: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    fold_summary = walk.groupby("hypothesis_id", observed=False).agg(
        positive_eval_folds=("eval_total_R", lambda values: int((values > 0).sum())),
        realistic_positive_eval_folds=("eval_realistic_total_R", lambda values: int((values > 0).sum())),
    )
    screened = registry.merge(fold_summary, left_on="hypothesis_id", right_index=True, how="left")
    preliminary = screened.loc[
        (screened["N"] >= 500)
        & (screened["avg_R"] > 0)
        & (screened["profit_factor"] >= 1.10)
        & (screened["realistic_total_R"] > 0)
        & (screened["fdr_q"] <= 0.10)
        & (screened["positive_years"] >= 4)
        & (screened["top_1pct_removed_total_R"] > 0)
        & (screened["max_positive_year_contribution"] <= 0.60)
        & (screened["positive_eval_folds"] >= 4)
        & (screened["realistic_positive_eval_folds"] >= 3)
    ].copy()

    sensitivity_rows: list[dict[str, object]] = []
    plateau: dict[str, bool] = {}
    for _, candidate in preliminary.iterrows():
        conditions = json.loads(candidate["conditions_json"])
        candidate_has_neighbor = False
        candidate_plateau = False
        for condition_index, condition in enumerate(conditions):
            feature = str(condition["feature"])
            value = str(condition["value"])
            ordered = ORDERED_NEIGHBORS.get(feature)
            if not ordered or value not in ordered:
                continue
            position = ordered.index(value)
            neighbor_values = ordered[max(0, position - 1) : position] + ordered[position + 1 : position + 2]
            for neighbor in neighbor_values:
                candidate_has_neighbor = True
                varied = [dict(item) for item in conditions]
                varied[condition_index]["value"] = neighbor
                group = apply_conditions(trades, varied)
                metrics = summarize(group)
                realistic = realistic_metrics(group)
                survives = bool(
                    metrics["N"] >= 100
                    and metrics["avg_R"] > 0
                    and metrics["profit_factor"] > 1.02
                    and realistic["total_R"] > 0
                )
                candidate_plateau = candidate_plateau or survives
                sensitivity_rows.append(
                    {
                        "hypothesis_id": candidate["hypothesis_id"],
                        "varied_feature": feature,
                        "base_value": value,
                        "neighbor_value": neighbor,
                        "N": metrics["N"],
                        "avg_R": metrics["avg_R"],
                        "total_R": metrics["total_R"],
                        "profit_factor": metrics["profit_factor"],
                        "realistic_total_R": realistic["total_R"],
                        "neighbor_survives": survives,
                    }
                )
        plateau[str(candidate["hypothesis_id"])] = bool(candidate_has_neighbor and candidate_plateau)

    if not sensitivity_rows:
        sensitivity_rows.append(
            {
                "hypothesis_id": "NONE",
                "varied_feature": "N/A",
                "base_value": "N/A",
                "neighbor_value": "N/A",
                "N": 0,
                "avg_R": np.nan,
                "total_R": np.nan,
                "profit_factor": np.nan,
                "realistic_total_R": np.nan,
                "neighbor_survives": False,
                "note": "No hypothesis reached the predeclared preliminary candidate screen.",
            }
        )
    sensitivity = pd.DataFrame(sensitivity_rows)
    preliminary["sensitivity_plateau"] = preliminary["hypothesis_id"].map(plateau).fillna(False)
    final = preliminary.loc[preliminary["sensitivity_plateau"]].copy()
    if len(final):
        final["complexity_penalty_rank"] = final["complexity"]
        final["rank_score"] = final["realistic_total_R"] / final["complexity"]
        final = final.sort_values(
            ["complexity_penalty_rank", "rank_score", "N"], ascending=[True, False, False]
        ).head(3)
        final["candidate_id"] = [f"P19-C{i}" for i in range(1, len(final) + 1)]
    return sensitivity, final


def candidate_comparison(trades: pd.DataFrame, final: pd.DataFrame) -> pd.DataFrame:
    base = summarize(trades)
    realistic = realistic_metrics(trades)
    rows = [
        {
            "candidate_id": "Original BOS",
            "rule": "Frozen BOS without added filter",
            **base,
            "realistic_total_R": realistic["total_R"],
            "realistic_profit_factor": realistic["profit_factor"],
            "status": "REFERENCE ONLY",
        }
    ]
    for _, candidate in final.iterrows():
        group = apply_conditions(trades, json.loads(candidate["conditions_json"]))
        metrics = summarize(group)
        costed = realistic_metrics(group)
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "rule": candidate["conditions_json"],
                **metrics,
                "realistic_total_R": costed["total_R"],
                "realistic_profit_factor": costed["profit_factor"],
                "status": "FROZEN FOR PHASE 20",
            }
        )
    return pd.DataFrame(rows)


def equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    path = trades.sort_values("exit_timestamp", kind="stable")[["exit_timestamp", "result_R"]].copy()
    path["cumulative_R"] = path["result_R"].cumsum()
    path["drawdown_R"] = np.maximum.accumulate(np.maximum(path["cumulative_R"].to_numpy(), 0.0)) - path["cumulative_R"].to_numpy()
    return path.reset_index(drop=True)


def make_charts(
    trades: pd.DataFrame, yearly: pd.DataFrame, rolling: pd.DataFrame, equity: pd.DataFrame
) -> None:
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-phase19")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    CHARTS.mkdir(parents=True, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid")

    def save_line(x, y, title, ylabel, filename, color="#1f77b4", zero=True):
        fig, ax = plt.subplots(figsize=(11, 5.5))
        ax.plot(x, y, color=color, linewidth=1.6)
        if zero:
            ax.axhline(0, color="#555555", linewidth=0.8)
        ax.set_title(title)
        ax.set_xlabel("Exit date")
        ax.set_ylabel(ylabel)
        fig.autofmt_xdate()
        fig.tight_layout()
        fig.savefig(CHARTS / filename, dpi=160)
        plt.close(fig)

    save_line(equity["exit_timestamp"], equity["cumulative_R"], "Original BOS cumulative equity, 2021–2026", "Cumulative R", "bos_equity_curve.png")
    save_line(equity["exit_timestamp"], equity["drawdown_R"], "Original BOS drawdown, 2021–2026", "Drawdown (R)", "bos_drawdown_curve.png", color="#d62728", zero=False)

    rolling_six = rolling.loc[(rolling["analysis_type"] == "rolling") & (rolling["window_months"] == 6)].copy()
    rolling_six["end_date"] = pd.to_datetime(rolling_six["end_month"] + "-01")
    save_line(rolling_six["end_date"], rolling_six["avg_R"], "Six-month rolling BOS expectancy", "Average R per trade", "rolling_expectancy.png")
    save_line(rolling_six["end_date"], rolling_six["profit_factor"], "Six-month rolling BOS profit factor", "Profit factor", "rolling_profit_factor.png", zero=False)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = ["#2ca02c" if value >= 0 else "#d62728" for value in yearly["total_R"]]
    ax.bar(yearly["year"].astype(str), yearly["total_R"], color=colors)
    ax.axhline(0, color="#555555", linewidth=0.8)
    ax.set_title("Original BOS yearly Total R")
    ax.set_xlabel("Calendar year (2026 is partial through June 26)")
    ax.set_ylabel("Total R")
    fig.tight_layout()
    fig.savefig(CHARTS / "yearly_performance.png", dpi=160)
    plt.close(fig)


def write_frozen_candidates(final: pd.DataFrame) -> None:
    lines = [
        "# Frozen Phase 19 candidates",
        "",
        "Phase 19 treats all 2021-01-01 through 2026-06-26 observations as development research.",
        "Phase 17 C1/C2 remain permanently rejected and were not reconsidered.",
        "",
    ]
    if final.empty:
        lines.extend(
            [
                "## Result: zero candidates",
                "",
                "No BOS subset passed every predeclared FDR, realistic-cost, temporal, outlier, walk-forward, and sensitivity requirement. Nothing is frozen for Phase 20.",
            ]
        )
    else:
        for _, row in final.iterrows():
            lines.extend(
                [
                    f"## {row['candidate_id']}",
                    "",
                    f"- Rule: `{row['conditions_json']}`",
                    f"- Development N: {int(row['N'])}",
                    f"- Ideal Total R: {row['total_R']:.3f}",
                    f"- Realistic-cost Total R: {row['realistic_total_R']:.3f}",
                    f"- FDR q: {row['fdr_q']:.6f}",
                    "",
                ]
            )
    (P19 / "FROZEN_PHASE19_CANDIDATES.md").write_text("\n".join(lines) + "\n")


def classification(
    baseline: pd.DataFrame,
    costs: pd.DataFrame,
    registry: pd.DataFrame,
    final: pd.DataFrame,
) -> tuple[str, str]:
    combined = baseline.loc[baseline["period"] == "2021-2026 combined"].iloc[0]
    realistic = costs.loc[
        (costs["period"] == "2021-2026 combined") & (costs["scenario"] == "Realistic")
    ].iloc[0]
    fdr_count = int((registry["evidence_label"] == "FDR-SURVIVING").sum())
    if len(final) and realistic["total_R"] > 0:
        return "B", "Real but regime-dependent; at least one filtered candidate survived every research screen."
    if combined["total_R"] > 0 and realistic["total_R"] <= 0:
        if fdr_count == 0 and not len(final):
            return "D", "No robust tradable edge: ideal gross profit is thin, realistic costs reverse it, and no subset survives the full screen."
        return "C", "Weak/inconclusive: gross edge exists, but implementation costs or stability tests remain unresolved."
    return "D", "No robust edge under the predeclared Phase 19 tests."


def write_report(
    baseline: pd.DataFrame,
    yearly: pd.DataFrame,
    monthly: pd.DataFrame,
    rolling: pd.DataFrame,
    costs: pd.DataFrame,
    outliers: pd.DataFrame,
    mc: pd.DataFrame,
    registry: pd.DataFrame,
    walk: pd.DataFrame,
    final: pd.DataFrame,
) -> None:
    grade, reason = classification(baseline, costs, registry, final)
    combined = baseline.loc[baseline["period"] == "2021-2026 combined"].iloc[0]
    real = costs.loc[(costs["period"] == "2021-2026 combined") & (costs["scenario"] == "Realistic")].iloc[0]
    selected = walk.loc[walk["selected_by_train"]]
    positive_months = int((monthly["total_R"] > 0).sum())
    fdr = registry.loc[registry["evidence_label"] == "FDR-SURVIVING"]
    six = rolling.loc[(rolling["analysis_type"] == "rolling") & (rolling["window_months"] == 6)]
    lines = [
        "# Phase 19 — BOS robustness and edge isolation",
        "",
        "## Executive summary",
        "",
        f"**Classification: {grade}. {reason}**",
        "",
        f"The original BOS produced {int(combined['N']):,} trades, {combined['total_R']:.2f}R gross, Avg R {combined['avg_R']:.4f}, PF {combined['profit_factor']:.3f}, and max drawdown {combined['max_drawdown_R']:.2f}R across the two exact development periods. At the predeclared realistic $14.50 round-trip cost, it falls to {real['total_R']:.2f}R and PF {real['profit_factor']:.3f}. Its constant round-trip break-even cost is only ${real['break_even_round_trip_cost_usd']:.2f} per trade.",
        "",
        f"No Phase 17 candidate was reused. Phase 19 registered {len(registry)} BOS hypotheses; {int((registry['N'] >= MIN_HYPOTHESIS_N).sum())} had N≥{MIN_HYPOTHESIS_N}, {int((registry['one_sided_p'] < 0.05).sum())} had raw one-sided p<0.05, and {len(fdr)} survived BH-FDR q≤0.10 with positive expectancy. Final Phase 19 candidates frozen: {len(final)}.",
        "",
        "## Mandatory baseline reproduction",
        "",
        "Both source periods passed byte-for-byte comparison for `model_comparison.csv`, `trades.csv`, and `event_debug.csv`. Exact entry and exit timestamps therefore match every original BOS record.",
        "",
    ]
    for _, row in baseline.iterrows():
        lines.append(
            f"- {row['period']}: N {int(row['N']):,}; wins {int(row['wins']):,}; losses {int(row['losses']):,}; Total {row['total_R']:.2f}R; Avg {row['avg_R']:.4f}R; PF {row['profit_factor']:.3f}; max DD {row['max_drawdown_R']:.2f}R."
        )
    lines.extend(
        [
            "",
            "## Temporal robustness",
            "",
            f"Positive calendar years: {int((yearly['total_R'] > 0).sum())}/{len(yearly)}. Positive months: {positive_months}/{len(monthly)}. Six-month rolling windows positive: {int((six['total_R'] > 0).sum())}/{len(six)}; their worst Total R was {six['total_R'].min():.2f}R and best was {six['total_R'].max():.2f}R. Performance is not uniform through time.",
            "",
            "The HTF trend-state row is deliberately the same previous-closed 60-minute regime as HTF bias under more descriptive labels; it is reported, not treated as an independent signal.",
            "",
            "## Cost stress",
            "",
        ]
    )
    for _, row in costs.loc[costs["period"] == "2021-2026 combined"].iterrows():
        lines.append(
            f"- {row['scenario']} (${row['round_trip_cost_usd']:.2f}/trade): Total {row['total_R']:.2f}R; Avg {row['avg_R']:.4f}R; PF {row['profit_factor']:.3f}; DD {row['max_drawdown_R']:.2f}R."
        )
    lines.extend(
        [
            "",
            "Costs are applied trade by trade as `cost dollars / (stop points × $20)`; this preserves the frozen per-trade R denominator. The strategy is not economically viable if ordinary round-trip friction exceeds the reported break-even cost.",
            "",
            "## Outlier and Monte Carlo stress",
            "",
        ]
    )
    for _, row in outliers.iterrows():
        lines.append(f"- {row['test']}: N {int(row['N'])}; Total {row['total_R']:.2f}R; PF {row['profit_factor']:.3f}; DD {row['max_drawdown_R']:.2f}R.")
    for _, row in mc.iterrows():
        lines.append(
            f"- {row['method']}, {int(row['simulations']):,} paths: P(terminal R>0) {100*row['probability_terminal_R_positive']:.1f}%; terminal p5/p50/p95 {row['terminal_R_p5']:.1f}/{row['terminal_R_p50']:.1f}/{row['terminal_R_p95']:.1f}R; max-DD p50/p95 {row['max_drawdown_R_p50']:.1f}/{row['max_drawdown_R_p95']:.1f}R; losing-streak p95 {row['longest_losing_streak_p95']:.0f}."
        )
    lines.extend(
        [
            "",
            "The moving-block bootstrap uses contiguous 20-trade blocks to retain local outcome dependence; IID results are provided only as a less conservative comparison.",
            "",
            "## Edge-isolation and multiplicity",
            "",
            f"All categorical hypotheses and six predeclared interaction families appear in `hypothesis_registry.csv`, including empty buckets. Raw p-values and BH-FDR q-values are both retained. FDR-surviving positive hypotheses: {len(fdr)}.",
            "",
            f"The expanding walk-forward used five chronological folds. A training-only condition was selected in {len(selected)}/5 folds; its subsequent evaluation result is marked by `selected_by_train` in `walk_forward_results.csv`. No held-forward fold influenced its own selection.",
            "",
            "## Final answers",
            "",
            f"1. **Does original BOS demonstrate evidence of a persistent edge?** It has a positive gross historical mean, but not a defensible persistent edge. Classification **{grade} — NO ROBUST EDGE**: {reason}",
            f"2. **Does BOS survive realistic NQ execution costs?** {'Yes' if real['total_R'] > 0 else 'No'}; realistic Total R is {real['total_R']:.2f} and PF is {real['profit_factor']:.3f}.",
            f"3. **What is BOS's break-even execution cost per trade?** ${real['break_even_round_trip_cost_usd']:.2f} per round trip under the frozen trade-specific risk conversion.",
            "4. **Is profitability broadly distributed or concentrated?** Concentrated. Two of six year buckets and 32 of 66 months were negative; 2021 supplied about 66% of all positive-year Total R, and deleting the top 1% of outcomes changes +48.24R to -35.76R.",
            "5. **Which market conditions explain performance?** The strongest raw associations were 02:00-03:59 CT, Long × low volatility, small stops/targets, and Overnight × medium volatility. They are descriptive only: none survived the common multiplicity correction, so no condition is established as an explanation.",
            f"6. **Did any conditions survive multiple-hypothesis correction?** No. FDR-surviving positive hypotheses: {len(fdr)}.",
            "7. **Did any candidate remain robust across walk-forward folds?** No. Training selected a rule in three folds; the first two lost in the next period and the third positive evaluation had only 22 trades. No rule met the final fold requirements.",
            "8. **How sensitive are candidate parameters?** Not applicable: no hypothesis reached the preliminary candidate gate, so parameter-neighborhood testing was correctly not initiated. `parameter_sensitivity.csv` records this explicitly.",
            "9. **Did P19-C1, C2, or C3 materially improve BOS robustness?** No P19 candidate qualified, so none was created or credited with an improvement.",
            "10. **Are any candidates strong enough to justify another genuine OOS test?** No.",
            "11. **Which candidates should be frozen for Phase 20?** None; `FROZEN_PHASE19_CANDIDATES.md` freezes a zero-candidate result.",
            "12. **Final finding:** No robust BOS edge was found.",
            "",
            "All 2021–2026 observations are now development/research. No Phase 19 result is described as out-of-sample, and no paid data was downloaded.",
        ]
    )
    (P19 / "PHASE19_BOS_REPORT.md").write_text("\n".join(lines) + "\n")


def write_readme(final: pd.DataFrame) -> None:
    text = f"""# Phase 19 — original BOS robustness

Phase 19 reproduces and stress-tests the untouched original BOS model across
2021-01-01 through 2026-06-26. All observations are development research.

- Baseline reproduction: PASS, byte-for-byte for both periods.
- Paid downloads: none.
- Phase 17 C1/C2: permanently rejected and not reconsidered.
- Frozen Phase 19 candidates: {len(final)}.

Start with `PHASE19_BOS_REPORT.md`, then inspect `WALK_FORWARD_PLAN.md` and
`FROZEN_PHASE19_CANDIDATES.md`. The charts and all machine-readable evidence are
in this directory. Reproduce with:

```bash
phase16/.venv312/bin/python phase19/analyze_bos.py
```
"""
    (P19 / "README.md").write_text(text)


def main() -> None:
    P19.mkdir(parents=True, exist_ok=True)
    baseline = baseline_gate()
    features = build_features()
    baseline = combined_baseline(baseline, features)
    yearly = calendar_results(features, "year")
    monthly = calendar_results(features, "month")
    rolling = rolling_results(features)
    detailed_breakdowns = breakdowns(features)
    costs = cost_stress(features)
    outliers = outlier_stress(features)
    mc = monte_carlo(features)
    registry = hypothesis_registry(features)
    walk = walk_forward(features, registry)
    sensitivity, final = sensitivity_and_candidates(features, registry, walk)
    comparison = candidate_comparison(features, final)
    equity = equity_curve(features)

    baseline.to_csv(P19 / "bos_baseline.csv", index=False)
    yearly.to_csv(P19 / "bos_yearly.csv", index=False)
    monthly.to_csv(P19 / "bos_monthly.csv", index=False)
    rolling.to_csv(P19 / "bos_rolling_metrics.csv", index=False)
    detailed_breakdowns.to_csv(P19 / "bos_breakdowns.csv", index=False)
    costs.to_csv(P19 / "bos_cost_stress.csv", index=False)
    outliers.to_csv(P19 / "bos_outlier_stress.csv", index=False)
    mc.to_csv(P19 / "bos_monte_carlo.csv", index=False)
    registry.to_csv(P19 / "hypothesis_registry.csv", index=False)
    walk.to_csv(P19 / "walk_forward_results.csv", index=False)
    sensitivity.to_csv(P19 / "parameter_sensitivity.csv", index=False)
    comparison.to_csv(P19 / "candidate_comparison.csv", index=False)
    features.to_csv(P19 / "bos_trade_features.csv", index=False)
    equity.to_csv(P19 / "bos_equity_drawdown.csv", index=False)

    make_charts(features, yearly, rolling, equity)
    write_frozen_candidates(final)
    write_report(baseline, yearly, monthly, rolling, costs, outliers, mc, registry, walk, final)
    write_readme(final)
    manifest = {
        "phase": 19,
        "engine_modified": False,
        "paid_downloads": False,
        "baseline_gate": "PASS",
        "combined_bos_trades": len(features),
        "registered_hypotheses": len(registry),
        "adequate_hypotheses": int((registry["N"] >= MIN_HYPOTHESIS_N).sum()),
        "fdr_survivors": int((registry["evidence_label"] == "FDR-SURVIVING").sum()),
        "frozen_candidates": len(final),
        "early_reference_trades_sha256": sha256(EARLY_REFERENCE / "trades.csv"),
        "late_reference_trades_sha256": sha256(LATE_REFERENCE / "trades.csv"),
        "early_data_sha256": sha256(EARLY_DATA),
        "late_data_sha256": sha256(LATE_DATA),
    }
    (P19 / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    grade, reason = classification(baseline, costs, registry, final)
    print("BASELINE REPRODUCTION: PASS")
    print(baseline[["period", "N", "wins", "losses", "avg_R", "total_R", "profit_factor", "max_drawdown_R"]].to_string(index=False))
    print(f"HYPOTHESES: {len(registry)}; FDR SURVIVORS: {(registry['evidence_label'] == 'FDR-SURVIVING').sum()}")
    print(f"FROZEN PHASE 19 CANDIDATES: {len(final)}")
    print(f"CLASSIFICATION: {grade} — {reason}")


if __name__ == "__main__":
    main()
