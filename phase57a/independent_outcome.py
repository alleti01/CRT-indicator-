"""Independent outcome engine — built from scratch, NOT reusing Phase57's simulate_trade."""

from __future__ import annotations

import numpy as np
import pandas as pd

ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0


def independent_cost_r(entry: float, stop: float, mult: float = 1.0) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return (ROUND_TURN_COST_USD * mult) / (risk * NQ_DOLLARS_PER_POINT)


def independent_simulate(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    atr: np.ndarray,
    entry_i: int,
    direction: str,
    stop_atr: float = 0.75,
    target_r: float = 2.5,
    max_hold: int = 60,
    cost_mult: float = 1.0,
) -> dict:
    """Completely independent trade simulation from raw arrays."""
    n = len(hi)
    i = int(entry_i)
    if i >= n - 1:
        return {"gross_R": np.nan, "net_R": np.nan, "exit_reason": "INVALID"}
    a = float(atr[i])
    d = 1 if direction == "LONG" else -1
    ep = float(cl[i])
    risk = stop_atr * a
    if risk <= 0:
        return {"gross_R": np.nan, "net_R": np.nan, "exit_reason": "ZERO_RISK"}
    stop = ep - risk if d == 1 else ep + risk
    target = ep + target_r * risk if d == 1 else ep - target_r * risk
    mfe = mae = 0.0
    realized = np.nan
    exit_i = i
    exit_reason = "NONE"
    limit = min(n, i + 1 + max_hold)
    for j in range(i + 1, limit):
        h, l, c = float(hi[j]), float(lo[j]), float(cl[j])
        if d == 1:
            mfe = max(mfe, (h - ep) / risk)
            mae = max(mae, (ep - l) / risk)
            hit_stop = l <= stop
            hit_tgt = h >= target
        else:
            mfe = max(mfe, (ep - l) / risk)
            mae = max(mae, (h - ep) / risk)
            hit_stop = h >= stop
            hit_tgt = l <= target
        # Conservative: stop before target on same bar
        if hit_stop:
            realized = -1.0
            exit_i = j
            exit_reason = "STOP"
            break
        if hit_tgt:
            realized = target_r
            exit_i = j
            exit_reason = "TARGET"
            break
        if j == limit - 1:
            realized = (c - ep) / risk * d
            exit_i = j
            exit_reason = "TIME"
    cr = independent_cost_r(ep, stop, cost_mult)
    return {
        "entry_i": i,
        "entry_price": ep,
        "direction": direction,
        "stop": stop,
        "target": target,
        "exit_i": exit_i,
        "exit_reason": exit_reason,
        "gross_R": realized,
        "cost_R": cr,
        "net_R": realized - cr if not np.isnan(realized) else np.nan,
        "MFE_R": mfe,
        "MAE_R": mae,
        "same_bar_collision": False,
    }
