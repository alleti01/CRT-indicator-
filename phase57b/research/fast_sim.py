"""Fast vectorized trade simulation — extract arrays once, simulate all trades.

Drop-in replacement for phase57.research.outcomes.batch_simulate but
extracts numpy arrays once and passes them to a tight inner loop.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r as _cost_r
from phase57b.config import STOP_ATR, TARGET_R, MAX_HOLD_MIN


def _sim_one(hi, lo, cl, atr_arr, n, entry_i, direction, stop_atr, target_r, max_hold, cost_mult):
    i = int(entry_i)
    if i >= n - 1 or i < 0:
        return (i, np.nan, np.nan, np.nan, 0.0, 0.0, i, "INVALID")
    a = float(atr_arr[i])
    d = 1 if direction == "LONG" else -1
    ep = float(cl[i])
    risk = stop_atr * a
    if risk <= 0:
        return (i, ep, np.nan, np.nan, 0.0, 0.0, i, "ZERO_RISK")
    stop = ep - risk if d == 1 else ep + risk
    target = ep + target_r * risk if d == 1 else ep - target_r * risk
    mfe = mae = 0.0
    realized = 0.0
    exit_i = i
    exit_reason = "NONE"
    end = min(n, i + 1 + max_hold)
    for j in range(i + 1, end):
        h, l, c = hi[j], lo[j], cl[j]
        if d == 1:
            mfe = max(mfe, (h - ep) / risk)
            mae = max(mae, (ep - l) / risk)
            if l <= stop:
                return (i, ep, -1.0, -1.0 - _cost_r(ep, stop, cost_mult), mfe, mae, j, "STOP")
            if h >= target:
                return (i, ep, target_r, target_r - _cost_r(ep, stop, cost_mult), mfe, mae, j, "TARGET")
        else:
            mfe = max(mfe, (ep - l) / risk)
            mae = max(mae, (h - ep) / risk)
            if h >= stop:
                return (i, ep, -1.0, -1.0 - _cost_r(ep, stop, cost_mult), mfe, mae, j, "STOP")
            if l <= target:
                return (i, ep, target_r, target_r - _cost_r(ep, stop, cost_mult), mfe, mae, j, "TARGET")
        if j == end - 1:
            realized = (c - ep) / risk * d
            cr = _cost_r(ep, stop, cost_mult)
            return (i, ep, realized, realized - cr, mfe, mae, j, "TIME")
    cr = _cost_r(ep, stop, cost_mult)
    return (i, ep, 0.0, -cr, mfe, mae, i, "NONE")


def fast_batch_simulate(
    m1: pd.DataFrame,
    entries: pd.DataFrame,
    *,
    stop_atr: float = STOP_ATR,
    target_r: float = TARGET_R,
    max_hold: int = MAX_HOLD_MIN,
    cost_mult: float = 1.0,
) -> pd.DataFrame:
    """Simulate trades with arrays extracted ONCE."""
    if entries.empty:
        return pd.DataFrame()
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    entry_is = entries["entry_i"].values.astype(int)
    dirs = entries["direction"].values
    k = len(entry_is)
    out_entry_i = np.empty(k, dtype=int)
    out_entry_price = np.empty(k)
    out_gross = np.empty(k)
    out_net = np.empty(k)
    out_mfe = np.empty(k)
    out_mae = np.empty(k)
    out_exit_i = np.empty(k, dtype=int)
    out_reason = np.empty(k, dtype=object)
    for idx in range(k):
        r = _sim_one(hi, lo, cl, atr_arr, n, entry_is[idx], dirs[idx],
                     stop_atr, target_r, max_hold, cost_mult)
        out_entry_i[idx] = r[0]
        out_entry_price[idx] = r[1]
        out_gross[idx] = r[2]
        out_net[idx] = r[3]
        out_mfe[idx] = r[4]
        out_mae[idx] = r[5]
        out_exit_i[idx] = r[6]
        out_reason[idx] = r[7]
    return pd.DataFrame({
        "entry_i": out_entry_i,
        "entry_price": out_entry_price,
        "direction": dirs,
        "gross_R": out_gross,
        "net_R": out_net,
        "MFE_R": out_mfe,
        "MAE_R": out_mae,
        "exit_i": out_exit_i,
        "exit_reason": out_reason,
    })


def fast_one_position(
    m1: pd.DataFrame,
    entries: pd.DataFrame,
    *,
    stop_atr: float = STOP_ATR,
    target_r: float = TARGET_R,
    max_hold: int = MAX_HOLD_MIN,
    cost_mult: float = 1.0,
) -> pd.DataFrame:
    """One-position-at-a-time: simulate all, then filter sequentially by exit_i."""
    all_trades = fast_batch_simulate(m1, entries, stop_atr=stop_atr,
        target_r=target_r, max_hold=max_hold, cost_mult=cost_mult)
    if all_trades.empty:
        return all_trades
    sorted_idx = np.argsort(all_trades["entry_i"].values)
    ei = all_trades["entry_i"].values[sorted_idx]
    xi = all_trades["exit_i"].values[sorted_idx]
    keep = np.zeros(len(all_trades), dtype=bool)
    last_exit = -1
    for j in range(len(sorted_idx)):
        if ei[j] > last_exit:
            keep[sorted_idx[j]] = True
            last_exit = xi[j]
    return all_trades.loc[keep].reset_index(drop=True)
