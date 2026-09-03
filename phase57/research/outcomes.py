"""Standardized outcome labeling + move capture metric."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r
from phase57.config import MAX_HOLD_MIN, OUTCOME_HORIZONS, STOP_ATR, TARGET_R


def simulate_trade(
    m1: pd.DataFrame,
    entry_i: int,
    direction: str,
    *,
    stop_atr: float = STOP_ATR,
    target_r: float = TARGET_R,
    max_hold: int = MAX_HOLD_MIN,
    cost_mult: float = 1.0,
) -> dict:
    """Single standardized paper trade from bar entry_i."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    i = int(entry_i)
    atr = float(atr_arr[i])
    d = 1 if direction == "LONG" else -1
    ep = float(cl[i])
    risk = stop_atr * atr
    stop = ep - risk if d == 1 else ep + risk
    target = ep + target_r * risk if d == 1 else ep - target_r * risk
    mfe = mae = 0.0
    realized = 0.0
    exit_i = i
    exit_price = ep
    exit_reason = "NONE"
    end = min(n, i + 1 + max_hold)
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
        if hit_stop:
            realized = -1.0
            exit_i, exit_price, exit_reason = j, stop, "STOP"
            break
        if hit_tgt:
            realized = target_r
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
        "cost_R": cr,
        "net_R": realized - cr,
        "MFE_R": mfe,
        "MAE_R": mae,
    }


def batch_simulate(
    m1: pd.DataFrame,
    entries: pd.DataFrame,
    **kwargs,
) -> pd.DataFrame:
    """Simulate trades for a DataFrame of entries with entry_i and direction."""
    rows = []
    for _, r in entries.iterrows():
        rows.append(simulate_trade(m1, int(r["entry_i"]), r["direction"], **kwargs))
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def forward_excursion(
    m1: pd.DataFrame,
    entry_i: int,
    direction: str,
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
) -> dict:
    """MFE/MAE in ATR at each horizon — for move capture metric (LABEL ONLY)."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    i = int(entry_i)
    atr = float(atr_arr[i])
    ep = float(m1["close"].values[i])
    d = 1 if direction == "LONG" else -1
    out = {}
    for h in horizons:
        end = min(n, i + 1 + h)
        if end <= i + 1:
            out[f"mfe_{h}m_atr"] = np.nan
            out[f"mae_{h}m_atr"] = np.nan
            continue
        sl = slice(i + 1, end)
        if d == 1:
            mfe = (hi[sl].max() - ep) / atr if atr > 0 else np.nan
            mae = (ep - lo[sl].min()) / atr if atr > 0 else np.nan
        else:
            mfe = (ep - lo[sl].min()) / atr if atr > 0 else np.nan
            mae = (hi[sl].max() - ep) / atr if atr > 0 else np.nan
        out[f"mfe_{h}m_atr"] = mfe
        out[f"mae_{h}m_atr"] = mae
    return out


def move_capture(
    m1: pd.DataFrame,
    setup_i: int,
    entry_i: int,
    direction: str,
    horizon: int = 60,
) -> dict:
    """Measure how much of the total directional move remains after entry.

    LABEL ONLY — uses future price for evaluation. Never an input feature.
    """
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    d = 1 if direction == "LONG" else -1
    total_end = min(n, setup_i + 1 + horizon)
    if total_end <= setup_i + 1:
        return {"move_capture_pct": np.nan, "excursion_before_entry_atr": np.nan, "excursion_after_entry_atr": np.nan}
    atr = float(atr_arr[setup_i])
    setup_price = float(m1["close"].values[setup_i])
    entry_price = float(m1["close"].values[min(entry_i, n - 1)])
    total_sl = slice(setup_i + 1, total_end)
    if d == 1:
        total_mfe = (hi[total_sl].max() - setup_price) / atr if atr > 0 else np.nan
        excursion_before = (entry_price - setup_price) / atr if atr > 0 else 0.0
    else:
        total_mfe = (setup_price - lo[total_sl].min()) / atr if atr > 0 else np.nan
        excursion_before = (setup_price - entry_price) / atr if atr > 0 else 0.0
    excursion_before = max(0.0, excursion_before)
    if total_mfe is None or np.isnan(total_mfe) or total_mfe <= 0:
        capture = np.nan
    else:
        remaining = total_mfe - excursion_before
        capture = remaining / total_mfe
    entry_end = min(n, entry_i + 1 + horizon)
    if d == 1:
        after = (hi[entry_i + 1:entry_end].max() - entry_price) / atr if entry_end > entry_i + 1 and atr > 0 else np.nan
    else:
        after = (entry_price - lo[entry_i + 1:entry_end].min()) / atr if entry_end > entry_i + 1 and atr > 0 else np.nan
    return {
        "move_capture_pct": capture,
        "excursion_before_entry_atr": excursion_before,
        "excursion_after_entry_atr": after,
        "total_excursion_atr": total_mfe,
    }
