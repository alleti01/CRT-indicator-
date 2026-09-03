"""Future outcome labels and standardized trade simulation — batched."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r
from phase53.config import MAX_HOLD_MIN, OPPORTUNITY_DEFS, OUTCOME_HORIZONS, STOP_ATR, TARGET_R


def batch_simulate(m1: pd.DataFrame, ii: np.ndarray, directions: np.ndarray, *, cost_mult: float = 1.0) -> pd.DataFrame:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    n = len(m1)
    max_hold = MAX_HOLD_MIN
    net_r = np.full(len(ii), np.nan)
    mfe_r = np.full(len(ii), np.nan)
    mae_r = np.full(len(ii), np.nan)

    for k, (i, dsign) in enumerate(zip(ii, directions)):
        i = int(i)
        atr = float(atr_arr[i])
        if not np.isfinite(atr) or atr <= 0 or i >= n - 2:
            continue
        ep = float(cl[i])
        d = 1 if dsign == 1 or dsign == "LONG" else -1
        risk = STOP_ATR * atr
        stop = ep - risk if d == 1 else ep + risk
        target = ep + TARGET_R * risk if d == 1 else ep - TARGET_R * risk
        mfe = mae = 0.0
        realized = 0.0
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
                realized = (stop - ep) / risk * d
                break
            if hit_tgt:
                realized = TARGET_R
                break
            if j == end - 1:
                realized = (c - ep) / risk * d
        cr = cost_r(ep, stop, cost_mult)
        net_r[k] = realized - cr
        mfe_r[k] = mfe
        mae_r[k] = mae

    return pd.DataFrame({"net_R": net_r, "MFE_R": mfe_r, "MAE_R": mae_r})


def batch_forward(m1: pd.DataFrame, ii: np.ndarray, directions: np.ndarray, horizon: int) -> tuple[np.ndarray, np.ndarray]:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_arr = m1["atr"].values.astype(float)
    mfes = np.full(len(ii), np.nan)
    maes = np.full(len(ii), np.nan)
    for k, (i, dsign) in enumerate(zip(ii, directions)):
        i = int(i)
        atr = float(atr_arr[i])
        if not np.isfinite(atr) or atr <= 0:
            continue
        ep = float(cl[i])
        d = 1 if dsign == 1 or dsign == "LONG" else -1
        mfe = mae = 0.0
        for j in range(i + 1, min(len(m1), i + 1 + horizon)):
            if d == 1:
                mfe = max(mfe, (hi[j] - ep) / atr)
                mae = max(mae, (ep - lo[j]) / atr)
            else:
                mfe = max(mfe, (ep - lo[j]) / atr)
                mae = max(mae, (hi[j] - ep) / atr)
        mfes[k] = mfe
        maes[k] = mae
    return mfes, maes


def attach_outcomes(events: pd.DataFrame, m1: pd.DataFrame, *, cost_mult: float = 1.0) -> pd.DataFrame:
    if events.empty:
        return events
    ii = events["entry_i"].values
    dirs = events["direction"].values
    sim = batch_simulate(m1, ii, dirs, cost_mult=cost_mult)
    out = pd.concat([events.reset_index(drop=True), sim], axis=1)

    for h in OUTCOME_HORIZONS:
        mfe, mae = batch_forward(m1, ii, dirs, h)
        out[f"mfe_{h}m_atr"] = mfe
        out[f"mae_{h}m_atr"] = mae

    for od in OPPORTUNITY_DEFS:
        mfe, mae = batch_forward(m1, ii, dirs, od["horizon_min"])
        if od.get("use_r"):
            out[f"opp_{od['name']}"] = ((out["net_R"] >= od["mfe_r"]) & (out["MAE_R"] <= od["mae_r"])).astype(int)
        else:
            out[f"opp_{od['name']}"] = ((mfe >= od["mfe_atr"]) & (mae < od["mae_atr"])).astype(int)
    return out
