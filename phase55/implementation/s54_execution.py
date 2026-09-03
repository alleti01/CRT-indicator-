"""S54 standardized execution with full exit audit trail."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r
from phase53.config import MAX_HOLD_MIN, STOP_ATR, TARGET_R


def simulate_trade(
    m1: pd.DataFrame,
    entry_i: int,
    direction: str,
    *,
    cost_mult: float = 1.0,
) -> dict:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    i = int(entry_i)
    atr = float(atr_arr[i])
    d = 1 if direction == "LONG" else -1
    ep = float(cl[i])
    risk = STOP_ATR * atr
    stop = ep - risk if d == 1 else ep + risk
    target = ep + TARGET_R * risk if d == 1 else ep - TARGET_R * risk
    mfe = mae = 0.0
    realized = 0.0
    exit_i = i
    exit_price = ep
    exit_reason = "NONE"
    ambiguous = False
    end = min(n, i + 1 + MAX_HOLD_MIN)
    for j in range(i + 1, end):
        h, l, c = hi[j], lo[j], cl[j]
        if d == 1:
            bar_mfe = (h - ep) / risk
            bar_mae = (ep - l) / risk
            hit_stop = l <= stop
            hit_tgt = h >= target
        else:
            bar_mfe = (ep - l) / risk
            bar_mae = (h - ep) / risk
            hit_stop = h >= stop
            hit_tgt = l <= target
        mfe = max(mfe, bar_mfe)
        mae = max(mae, bar_mae)
        if hit_stop and hit_tgt:
            ambiguous = True
        if hit_stop:
            realized = (stop - ep) / risk * d
            exit_i, exit_price, exit_reason = j, stop, "STOP"
            break
        if hit_tgt:
            realized = TARGET_R
            exit_i, exit_price, exit_reason = j, target, "TARGET"
            break
        if j == end - 1:
            realized = (c - ep) / risk * d
            exit_i, exit_price, exit_reason = j, c, "TIME"
    cr = cost_r(ep, stop, cost_mult)
    return {
        "entry_i": i,
        "entry_price": ep,
        "entry_timestamp": m1.index[i],
        "direction": direction,
        "atr": atr,
        "stop": stop,
        "target": target,
        "exit_i": exit_i,
        "exit_timestamp": m1.index[exit_i],
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_R": realized,
        "net_R": realized - cr,
        "MFE_R": mfe,
        "MAE_R": mae,
        "same_bar_ambiguous": ambiguous,
    }


def simulate_trades(m1: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in entries.iterrows():
        rows.append(simulate_trade(m1, int(r["entry_i"]), r["direction"]))
    return pd.DataFrame(rows)
