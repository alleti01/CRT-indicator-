"""Drawdown reconstruction — multiple methods."""
from __future__ import annotations

import numpy as np
import pandas as pd


def closed_trade_dd(trades: pd.DataFrame, r_col: str = "net_R") -> float:
    t = trades.sort_values("exit_i")
    eq = t[r_col].cumsum()
    peak = eq.cummax()
    return float((peak - eq).max())


def entry_order_dd(trades: pd.DataFrame, r_col: str = "net_R") -> float:
    t = trades.sort_values("entry_i")
    eq = t[r_col].cumsum()
    peak = eq.cummax()
    return float((peak - eq).max())


def mtm_portfolio_dd(trades: pd.DataFrame, n_bars: int, r_col: str = "net_R") -> float:
    """Minute mark-to-market: sum unrealized R for open positions + realized."""
    if trades.empty:
        return 0.0
    realized = np.zeros(n_bars, dtype=float)
    for _, t in trades.iterrows():
        ei, ex = int(t["entry_i"]), int(t["exit_i"])
        realized[ex] += t[r_col]
    # approximate open exposure: linear interpolation of final R (diagnostic lower bound)
    exposure = np.zeros(n_bars, dtype=float)
    for _, t in trades.iterrows():
        ei, ex = int(t["entry_i"]), int(t["exit_i"])
        if ex <= ei:
            continue
        slope = t[r_col] / max(1, ex - ei)
        for i in range(ei + 1, min(ex, n_bars)):
            exposure[i] += slope * (i - ei)
    equity = np.cumsum(realized) + exposure
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def loss_streaks(trades: pd.DataFrame, r_col: str = "net_R") -> dict:
    rs = trades.sort_values("exit_i")[r_col].values
    max_streak = cur = 0
    for r in rs:
        if r <= 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0
    roll20 = pd.Series(rs).rolling(20).sum().min() if len(rs) >= 20 else np.nan
    roll100 = pd.Series(rs).rolling(100).sum().min() if len(rs) >= 100 else np.nan
    return {
        "max_consecutive_losses": max_streak,
        "min_roll_20": float(roll20) if np.isfinite(roll20) else np.nan,
        "min_roll_100": float(roll100) if np.isfinite(roll100) else np.nan,
    }
