"""Standardized S52 exit simulation (fixed before candidate comparison)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r

from phase52.config import S52_MAX_HOLD_MIN, S52_STOP_ATR, S52_TARGET_R


def s52_levels(entry: float, atr: float, direction: str) -> tuple[float, float]:
    d = 1 if direction.upper() == "LONG" else -1
    risk = S52_STOP_ATR * atr
    if d == 1:
        stop = entry - risk
        target = entry + S52_TARGET_R * risk
    else:
        stop = entry + risk
        target = entry - S52_TARGET_R * risk
    return stop, target


def simulate_signals(
    market: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    cost_mult: float = 1.0,
) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    hi = market["high"].values.astype(float)
    lo = market["low"].values.astype(float)
    cl = market["close"].values.astype(float)
    atr_arr = market["atr"].values.astype(float) if "atr" in market.columns else np.full(len(market), np.nan)
    n = len(market)
    max_hold = S52_MAX_HOLD_MIN
    rows = []
    for _, sig in signals.iterrows():
        i = int(sig["entry_i"])
        if i >= n - 1:
            continue
        atr = float(atr_arr[i])
        if not np.isfinite(atr) or atr <= 0:
            continue
        ep = float(sig["entry_price"])
        stop, target = s52_levels(ep, atr, sig["direction"])
        d = 1 if sig["direction"].upper() == "LONG" else -1
        risk = abs(ep - stop) or 1e-9
        mfe = mae = 0.0
        exit_type = "DATA_END"
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
            if bar_mfe > mfe:
                mfe = bar_mfe
            if bar_mae > mae:
                mae = bar_mae
            if hit_stop:
                exit_type, realized = "STOP", (stop - ep) / risk * d
                break
            if hit_tgt:
                exit_type, realized = "TARGET", S52_TARGET_R
                break
            if j == end - 1:
                exit_type, realized = "TIME", (c - ep) / risk * d
        cr = cost_r(ep, stop, cost_mult)
        rows.append(
            {
                **sig.to_dict(),
                "gross_R": realized,
                "net_R": realized - cr,
                "cost_R": cr,
                "MFE_R": mfe,
                "MAE_R": mae,
                "exit_type": exit_type,
                "stop": stop,
                "target": target,
                "atr_entry": atr,
            }
        )
    return pd.DataFrame(rows)
