"""Metrics helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def pf(rs: pd.Series) -> float:
    wins = rs[rs > 0].sum()
    losses = rs[rs <= 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else np.nan
    return float(wins / abs(losses))


def max_dd(rs: pd.Series) -> float:
    if rs.empty:
        return np.nan
    eq = rs.cumsum()
    return float((eq.cummax() - eq).max())


def summarize_r(df: pd.DataFrame, r_col: str = "net_R") -> dict:
    if df.empty or r_col not in df.columns:
        return {"N": 0}
    rs = df[r_col].astype(float).dropna()
    days = max((df["timestamp_ct"].max() - df["timestamp_ct"].min()).days, 1) if "timestamp_ct" in df.columns else 1
    return {
        "N": len(rs),
        "trades_per_day": len(rs) / days,
        "AvgR": float(rs.mean()),
        "median_R": float(rs.median()),
        "PF": pf(rs),
        "TotalR": float(rs.sum()),
        "MaxDD": max_dd(rs),
        "win_rate": float((rs > 0).mean()),
        "MAE": float(df["MAE_R"].mean()) if "MAE_R" in df.columns else np.nan,
        "MFE": float(df["MFE_R"].mean()) if "MFE_R" in df.columns else np.nan,
    }
