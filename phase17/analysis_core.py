"""Causal feature engineering and statistical helpers for Phase 17.

Nothing in this module changes the frozen Phase 16 event or trade engines.  It
only annotates their completed-trade export with information known at entry.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from phase16.config import DEFAULT_CONFIG
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
    htf_regime_name,
    score_band,
    session_bucket_name,
)
from phase16.metrics import summarize_group


ROOT = Path(__file__).resolve().parents[1]
P16_RESULTS = ROOT / "phase16" / "results" / "oos"
RESULTS = ROOT / "phase17" / "results"
REPORTS = ROOT / "phase17" / "reports"
MODELS = ("Control", "BOS", "Retest", "Confirm")
RESEARCH_END = pd.Timestamp("2025-07-01", tz=DEFAULT_CONFIG.exchange_timezone)
VALIDATION_END = pd.Timestamp("2026-06-27", tz=DEFAULT_CONFIG.exchange_timezone)
MIN_MEANINGFUL_N = 30


def read_trades(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    timestamp_columns = [column for column in frame.columns if column.endswith("timestamp")]
    for column in timestamp_columns:
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce").dt.tz_convert(
            DEFAULT_CONFIG.exchange_timezone
        )
    return frame


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def max_drawdown(results: Sequence[float]) -> float:
    values = np.asarray(results, dtype=float)
    if not len(values):
        return 0.0
    equity = np.cumsum(values)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    return float(np.max(peaks - equity, initial=0.0))


def max_losing_streak(results: Sequence[float]) -> int:
    maximum = current = 0
    for value in results:
        current = current + 1 if float(value) < 0 else 0
        maximum = max(maximum, current)
    return maximum


def extended_summary(group: pd.DataFrame) -> dict[str, float | int]:
    ordered = group.sort_values("exit_timestamp", kind="stable") if not group.empty else group
    summary = summarize_group(ordered)
    values = ordered["result_R"].astype(float).to_numpy() if not ordered.empty else np.array([])
    n = len(values)
    sem = float(np.std(values, ddof=1) / math.sqrt(n)) if n >= 2 else float("nan")
    margin = 1.96 * sem if math.isfinite(sem) else float("nan")
    mean = float(np.mean(values)) if n else 0.0
    summary.update(
        {
            "flat": int(np.sum(values == 0)),
            "sem_R": sem,
            "ci95_low_R": mean - margin if math.isfinite(margin) else float("nan"),
            "ci95_high_R": mean + margin if math.isfinite(margin) else float("nan"),
            "adequate_sample": bool(n >= MIN_MEANINGFUL_N),
        }
    )
    return summary


def _session_name(value: int) -> str:
    return {
        "Opening": "Open",
        "Morning": "MidAM",
        "Afternoon": "PM",
    }.get(session_bucket_name(value), session_bucket_name(value))


def _date_third(timestamp: pd.Timestamp) -> str:
    start = pd.Timestamp("2024-01-01", tz=DEFAULT_CONFIG.exchange_timezone)
    end = VALIDATION_END
    position = (timestamp - start).total_seconds() / (end - start).total_seconds()
    return "Early third" if position < 1 / 3 else "Middle third" if position < 2 / 3 else "Late third"


def prepare_market_features(data_path: Path) -> pd.DataFrame:
    """Create only causal bar features; rolling thresholds are shifted one bar."""
    market = load_ohlcv_csv(data_path, exchange_timezone=DEFAULT_CONFIG.exchange_timezone)
    market = add_base_indicators(market, DEFAULT_CONFIG)
    market = add_previous_closed_htf_regime(market, DEFAULT_CONFIG)
    market = market.join(crt_reference_and_sweeps(market))
    market["normalized_atr"] = market["atr"] / market["close"]

    # Roughly 60 trading days of 24-hour five-minute bars.  shift(1) ensures the
    # current bar never helps classify itself.  The downloaded warm-up supplies
    # more than the 1,000 observations required at the OOS boundary.
    history = market["normalized_atr"].shift(1).rolling(17_280, min_periods=1_000)
    market["volatility_q33"] = history.quantile(1 / 3)
    market["volatility_q67"] = history.quantile(2 / 3)
    market["volatility_regime"] = np.select(
        [
            market["normalized_atr"] <= market["volatility_q33"],
            market["normalized_atr"] >= market["volatility_q67"],
        ],
        ["Low", "High"],
        default="Medium",
    )
    market.loc[market["volatility_q33"].isna(), "volatility_regime"] = "Unavailable"
    market["trend_regime"] = market["htf_regime"].map(
        {1: "Bullish trend", -1: "Bearish trend", 0: "Range/chop"}
    )
    past_volume = market["volume"].shift(1).rolling(288, min_periods=72)
    volume_mean = past_volume.mean()
    volume_std = past_volume.std().replace(0.0, np.nan)
    market["volume_zscore"] = (market["volume"] - volume_mean) / volume_std
    return market


def build_trade_features(trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    working = trades.copy()
    join_columns = [
        "atr",
        "body",
        "body_sma",
        "normalized_atr",
        "volatility_q33",
        "volatility_q67",
        "volatility_regime",
        "trend_regime",
        "crt_high",
        "crt_low",
        "sweep_above",
        "sweep_below",
        "volume",
        "volume_zscore",
    ]
    entry_rows = market[join_columns].reindex(pd.DatetimeIndex(working["entry_timestamp"]))
    entry_rows.index = working.index
    working = pd.concat([working, entry_rows], axis=1)
    working["direction_name"] = working["direction"]
    working["htf_regime_name"] = working["htf_regime"].map(htf_regime_name)
    working["session_name"] = working["session_bucket"].map(_session_name)
    working["score_band"] = working["score"].map(score_band)
    working["date_third"] = working["entry_timestamp"].map(_date_third)
    working["bos_present"] = working["bos_timestamp"].notna()
    working["retest_present"] = working["retest_timestamp"].notna()
    working["confirmation_present"] = working["confirm_timestamp"].notna()
    working["stop_distance_points"] = (working["entry_price"] - working["stop_price"]).abs()
    working["target_distance_points"] = (working["target_price"] - working["entry_price"]).abs()
    working["stop_distance_atr"] = working["stop_distance_points"] / working["atr"]
    working["stop_distance_pct"] = 100 * working["stop_distance_points"] / working["entry_price"]
    working["body_to_atr"] = working["body"] / working["atr"]
    working["time_since_setup_bars"] = (
        (working["entry_timestamp"] - working["setup_timestamp"]).dt.total_seconds() / 300
    )
    working["time_since_bos_bars"] = (
        (working["entry_timestamp"] - working["bos_timestamp"]).dt.total_seconds() / 300
    )
    working["time_since_retest_bars"] = (
        (working["entry_timestamp"] - working["retest_timestamp"]).dt.total_seconds() / 300
    )
    relevant_level = np.where(working["direction"] == "Long", working["crt_low"], working["crt_high"])
    working["relevant_crt_level"] = relevant_level
    working["distance_from_crt_points"] = (working["entry_price"] - relevant_level).abs()
    working["distance_from_crt_atr"] = working["distance_from_crt_points"] / working["atr"]
    working["outcome"] = np.where(
        working["result_R"] > 0, "Win", np.where(working["result_R"] < 0, "Loss", "Flat")
    )
    working["split"] = np.where(
        working["entry_timestamp"] < RESEARCH_END,
        "Research",
        np.where(working["entry_timestamp"] < VALIDATION_END, "Validation", "Outside"),
    )
    return working


DIMENSIONS: dict[str, tuple[str, list[str]]] = {
    "direction": ("direction_name", ["Long", "Short"]),
    "HTF_regime": ("htf_regime_name", ["Bull", "Bear", "Neutral"]),
    "session": ("session_name", ["Overnight", "Premarket", "Open", "MidAM", "Midday", "PM", "After-hours"]),
    "score_band": ("score_band", ["70-74", "75-79", "80-84", "85-89", "90-94", "95+"]),
    "date_third": ("date_third", ["Early third", "Middle third", "Late third"]),
    "volatility": ("volatility_regime", ["Low", "Medium", "High", "Unavailable"]),
    "trend_state": ("trend_regime", ["Bullish trend", "Bearish trend", "Range/chop"]),
}

INTERSECTIONS = (
    ("HTF_regime", "direction"),
    ("HTF_regime", "session"),
    ("HTF_regime", "score_band"),
    ("session", "direction"),
    ("session", "score_band"),
    ("direction", "score_band"),
)


def edge_map(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    intersections: list[dict[str, object]] = []
    for model in MODELS:
        model_group = features.loc[features["model"] == model]
        for dimension, (column, buckets) in DIMENSIONS.items():
            for bucket in buckets:
                group = model_group.loc[model_group[column] == bucket]
                rows.append({"model": model, "dimension": dimension, "bucket": bucket, **extended_summary(group)})
        for left_name, right_name in INTERSECTIONS:
            left_column, left_buckets = DIMENSIONS[left_name]
            right_column, right_buckets = DIMENSIONS[right_name]
            for left in left_buckets:
                for right in right_buckets:
                    group = model_group.loc[
                        (model_group[left_column] == left) & (model_group[right_column] == right)
                    ]
                    intersections.append(
                        {
                            "model": model,
                            "dimension": f"{left_name} x {right_name}",
                            "bucket": f"{left} | {right}",
                            "feature_1": left_column,
                            "value_1": left,
                            "feature_2": right_column,
                            "value_2": right,
                            **extended_summary(group),
                        }
                    )
    return pd.DataFrame(rows), pd.DataFrame(intersections)


def temporal_results(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = features.copy()
    local = working["entry_timestamp"]
    working["month"] = local.dt.strftime("%Y-%m")
    working["quarter"] = local.dt.tz_localize(None).dt.to_period("Q").astype(str)
    working["year"] = local.dt.strftime("%Y")
    calendar_rows: list[dict[str, object]] = []
    for model in MODELS:
        model_group = working.loc[working["model"] == model]
        for period, column in (("month", "month"), ("quarter", "quarter"), ("year", "year")):
            for bucket, group in model_group.groupby(column, sort=True):
                calendar_rows.append(
                    {"model": model, "period_type": period, "period": bucket, **extended_summary(group)}
                )

    rolling_rows: list[dict[str, object]] = []
    first_month = pd.Period("2024-01", freq="M")
    last_month = pd.Period("2026-06", freq="M")
    months = pd.period_range(first_month, last_month, freq="M")
    for model in MODELS:
        model_group = working.loc[working["model"] == model]
        entry_period = model_group["entry_timestamp"].dt.tz_localize(None).dt.to_period("M")
        for window in (3, 6, 12):
            for end_period in months[window - 1 :]:
                start_period = end_period - (window - 1)
                group = model_group.loc[(entry_period >= start_period) & (entry_period <= end_period)]
                rolling_rows.append(
                    {
                        "model": model,
                        "window_months": window,
                        "start_month": str(start_period),
                        "end_month": str(end_period),
                        **extended_summary(group),
                    }
                )
    return pd.DataFrame(calendar_rows), pd.DataFrame(rolling_rows)


def normal_one_sided_p(mean: float, sem: float) -> float:
    if not math.isfinite(sem) or sem <= 0:
        return 0.0 if mean > 0 else 1.0
    return float(1.0 - NormalDist().cdf(mean / sem))


def benjamini_hochberg(p_values: Iterable[float]) -> np.ndarray:
    values = np.asarray(list(p_values), dtype=float)
    if not len(values):
        return values
    order = np.argsort(values)
    ranked = values[order]
    adjusted = ranked * len(values) / np.arange(1, len(values) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.minimum(adjusted, 1.0)
    return output


def bootstrap_expectancy(values: np.ndarray, *, samples: int = 2_000, seed: int = 17) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    means = np.empty(samples, dtype=float)
    batch = 200
    for start in range(0, samples, batch):
        size = min(batch, samples - start)
        draws = rng.choice(values, size=(size, len(values)), replace=True)
        means[start : start + size] = draws.mean(axis=1)
    return (
        float(np.mean(means > 0)),
        float(np.quantile(means, 0.025)),
        float(np.quantile(means, 0.975)),
    )


def apply_spec(features: pd.DataFrame, spec: dict[str, object]) -> pd.DataFrame:
    group = features.loc[features["model"] == spec["model"]]
    for condition in spec["conditions"]:
        group = group.loc[group[str(condition["feature"])] == condition["value"]]
    return group


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, default=str) + "\n")

