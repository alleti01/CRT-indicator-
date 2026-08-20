"""Performance summaries, breakdowns, and R-multiple paths."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

import numpy as np
import pandas as pd

from .indicators import htf_regime_name, score_band, session_bucket_name
from .models import MODELS


SUMMARY_COLUMNS = [
    "model",
    "N",
    "wins",
    "losses",
    "win_pct",
    "avg_R",
    "total_R",
    "profit_factor",
    "max_drawdown_R",
    "largest_win_R",
    "largest_loss_R",
    "max_consecutive_wins",
    "max_consecutive_losses",
]


def _drawdown(results: pd.Series) -> float:
    if results.empty:
        return 0.0
    equity = results.astype(float).cumsum()
    peaks = pd.concat([pd.Series([0.0]), equity.reset_index(drop=True)]).cummax().iloc[1:]
    return float((peaks.to_numpy() - equity.to_numpy()).max(initial=0.0))


def _max_streak(results: Sequence[float], winning: bool) -> int:
    maximum = current = 0
    for result in results:
        matched = result > 0 if winning else result < 0
        current = current + 1 if matched else 0
        maximum = max(maximum, current)
    return maximum


def summarize_group(trades: pd.DataFrame) -> Dict[str, float | int]:
    results = trades["result_R"].astype(float) if not trades.empty else pd.Series(dtype=float)
    count = len(results)
    wins = int((results > 0).sum())
    losses = int((results < 0).sum())
    gross_profit = float(results[results > 0].sum())
    gross_loss = float(-results[results < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0)
    return {
        "N": count,
        "wins": wins,
        "losses": losses,
        "win_pct": wins * 100.0 / count if count else 0.0,
        "avg_R": float(results.mean()) if count else 0.0,
        "total_R": float(results.sum()) if count else 0.0,
        "profit_factor": float(profit_factor),
        "max_drawdown_R": _drawdown(results),
        "largest_win_R": float(results.max()) if count else 0.0,
        "largest_loss_R": float(results.min()) if count else 0.0,
        "max_consecutive_wins": _max_streak(results.tolist(), True),
        "max_consecutive_losses": _max_streak(results.tolist(), False),
    }


def model_summary(trades: pd.DataFrame, models: Iterable[str] = MODELS) -> pd.DataFrame:
    rows = []
    for model in models:
        group = trades.loc[trades["model"] == model].sort_values("exit_timestamp") if not trades.empty else trades
        rows.append({"model": model, **summarize_group(group)})
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


def monthly_results(trades: pd.DataFrame) -> pd.DataFrame:
    columns = ["model", "month", *SUMMARY_COLUMNS[1:]]
    if trades.empty:
        return pd.DataFrame(columns=columns)
    working = trades.copy()
    working["month"] = pd.to_datetime(working["exit_timestamp"]).dt.strftime("%Y-%m")
    rows = []
    for (model, month), group in working.groupby(["model", "month"], sort=True):
        rows.append({"model": model, "month": month, **summarize_group(group.sort_values("exit_timestamp"))})
    return pd.DataFrame(rows, columns=columns)


def robustness_breakdowns(trades: pd.DataFrame) -> pd.DataFrame:
    columns = ["model", "dimension", "bucket", *SUMMARY_COLUMNS[1:]]
    if trades.empty:
        return pd.DataFrame(columns=columns)
    working = trades.copy()
    entry = pd.to_datetime(working["entry_timestamp"])
    working["direction_bucket"] = working["direction"]
    working["month_bucket"] = entry.dt.strftime("%Y-%m")
    working["quarter_bucket"] = entry.dt.to_period("Q").astype(str)
    working["score_bucket"] = working["score"].map(score_band)
    working["session_bucket_name"] = working["session_bucket"].map(session_bucket_name)
    working["htf_regime_name"] = working["htf_regime"].map(htf_regime_name)
    dimensions = {
        "direction": "direction_bucket",
        "month": "month_bucket",
        "quarter": "quarter_bucket",
        "score_band": "score_bucket",
        "session": "session_bucket_name",
        "HTF_regime": "htf_regime_name",
    }
    rows = []
    for model, model_group in working.groupby("model", sort=False):
        for dimension, column in dimensions.items():
            for bucket, group in model_group.groupby(column, sort=True):
                rows.append(
                    {
                        "model": model,
                        "dimension": dimension,
                        "bucket": str(bucket),
                        **summarize_group(group.sort_values("exit_timestamp")),
                    }
                )
    return pd.DataFrame(rows, columns=columns)


def date_third_breakdowns(
    trades: pd.DataFrame, start: pd.Timestamp, end_exclusive: pd.Timestamp
) -> pd.DataFrame:
    """Reproduce Pine's entry-timestamp Early/Middle/Late date thirds."""
    columns = ["model", "dimension", "bucket", *SUMMARY_COLUMNS[1:]]
    if trades.empty:
        return pd.DataFrame(columns=columns)
    working = trades.copy()
    entry = pd.to_datetime(working["entry_timestamp"])
    span = (end_exclusive - start).total_seconds()
    elapsed = (entry - start).dt.total_seconds()
    segment = np.minimum(2, np.floor(elapsed * 3.0 / span)).astype(int)
    working["date_third"] = segment.map({0: "Early", 1: "Middle", 2: "Late"})
    rows = []
    for (model, bucket), group in working.groupby(["model", "date_third"], sort=False):
        rows.append(
            {
                "model": model,
                "dimension": "date_third",
                "bucket": bucket,
                **summarize_group(group.sort_values("exit_timestamp")),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def equity_path(trades: pd.DataFrame, model: str = "Retest") -> pd.DataFrame:
    columns = ["exit_timestamp", "result_R", "cumulative_R", "drawdown_R"]
    group = trades.loc[trades["model"] == model].sort_values("exit_timestamp") if not trades.empty else trades
    if group.empty:
        return pd.DataFrame(columns=columns)
    path = group[["exit_timestamp", "result_R"]].copy().reset_index(drop=True)
    path["cumulative_R"] = path["result_R"].astype(float).cumsum()
    path["drawdown_R"] = path["cumulative_R"].cummax().clip(lower=0.0) - path["cumulative_R"]
    return path[columns]
