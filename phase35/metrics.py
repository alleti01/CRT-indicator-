"""Reporting helpers for Phase 35."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from phase17.analysis_core import max_drawdown
from phase29.config import ROUND_TURN_COST_USD, NQ_DOLLARS_PER_POINT
from phase31.dedupe import rth_trading_dates
from phase31.metrics import apply_costs, net_performance, performance

from .config import FREQ_BANDS


def yearly_results(trades: pd.DataFrame, *, ts_col: str = "entry_timestamp") -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    df = trades.copy()
    df[ts_col] = pd.to_datetime(df[ts_col])
    df["year"] = df[ts_col].dt.year
    rows = []
    for year, grp in df.groupby("year"):
        perf = net_performance(grp.assign(entry_price=grp["entry_price"], stop_price=grp["stop_price"]))
        rows.append({"year": int(year), **perf})
    return pd.DataFrame(rows)


def direction_results(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for direction, grp in trades.groupby(trades["direction"].str.lower()):
        perf = net_performance(grp)
        days = grp["entry_timestamp"].dt.normalize().nunique() if "entry_timestamp" in grp.columns else 1
        rows.append(
            {
                "direction": direction.title(),
                **perf,
                "trades_day": len(grp) / max(days, 1),
            }
        )
    return pd.DataFrame(rows)


def cost_stress(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for mult in (1.0, 1.5, 2.0):
        df = trades.copy()
        df["net_R"] = apply_costs(df, multiplier=mult)
        perf = performance(df, col="net_R")
        rows.append({"cost_multiplier": mult, **perf})
    return pd.DataFrame(rows)


def outlier_robustness(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty or "net_R" not in trades.columns and "result_R" in trades.columns:
        trades = trades.copy()
        trades["net_R"] = apply_costs(trades)
    if trades.empty:
        return pd.DataFrame()
    r = trades["net_R"].astype(float)
    cutoff = r.quantile(0.99)
    trimmed = trades.loc[r <= cutoff]
    return pd.DataFrame(
        [
            {"slice": "full", **net_performance(trades)},
            {"slice": "exclude_top_1pct", **net_performance(trimmed)},
        ]
    )


def frequency_frontier(trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rth_days = len(rth_trading_dates(market))
    rows = []
    for band in FREQ_BANDS:
        rows.append(
            {
                "target_trades_day": band,
                "actual_trades_day": len(trades) / max(rth_days, 1),
                "net_AvgR": net_performance(trades)["AvgR"],
            }
        )
    return pd.DataFrame(rows)


def monotonic_precision(curve: pd.DataFrame) -> bool:
    if curve.empty or "top_pct" not in curve.columns:
        return False
    sub = curve.sort_values("top_pct", ascending=False)
    prec = sub["precision"].tolist()
    return all(prec[i] >= prec[i + 1] - 1e-9 for i in range(len(prec) - 1))
