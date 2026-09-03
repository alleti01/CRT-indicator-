"""Simulate frozen stop/target on 1m bars."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase39.classify import classify_behavior

from .config import MAX_HOLD_CONT, MAX_HOLD_REV
from .data_1m import cost_r


def _wrong_direction(mfe: float, mae: float, t05: float) -> int:
    row = pd.Series(
        {
            "MFE_R": mfe,
            "MAE_R": mae,
            "directional_efficiency": 0.5,
            "movement_efficiency": 0.5,
            "bars_to_plus_0.50r": t05,
        }
    )
    return int(classify_behavior(row) == "WRONG_DIRECTION")


def simulate_1m(
    market: pd.DataFrame,
    entry_i: int,
    entry_price: float,
    stop: float,
    target: float,
    direction: str,
    signal_type: str,
    *,
    cost_mult: float = 1.0,
) -> dict:
    d = 1 if str(direction).lower() == "long" else -1
    risk = abs(entry_price - stop) or 1e-9
    max_bars = MAX_HOLD_CONT if signal_type in ("L", "S") else MAX_HOLD_REV
    mfe = mae = 0.0
    bars_mfe = bars_mae = np.nan
    t05 = t1 = tstop = ttarget = np.nan
    exit_type = "DATA_END"
    exit_i = entry_i
    exit_px = entry_price
    realized = 0.0
    for elapsed, j in enumerate(range(entry_i + 1, min(len(market), entry_i + 1 + max_bars)), start=1):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        if d == 1:
            bar_mfe = (hi - entry_price) / risk
            bar_mae = (entry_price - lo) / risk
            hit_stop = lo <= stop
            hit_tgt = hi >= target
        else:
            bar_mfe = (entry_price - lo) / risk
            bar_mae = (hi - entry_price) / risk
            hit_stop = hi >= stop
            hit_tgt = lo <= target
        if bar_mfe > mfe:
            mfe, bars_mfe = bar_mfe, elapsed
        if bar_mae > mae:
            mae, bars_mae = bar_mae, elapsed
        if np.isnan(t05) and mfe >= 0.5:
            t05 = elapsed
        if np.isnan(t1) and mfe >= 1.0:
            t1 = elapsed
        if hit_stop:
            exit_type, exit_i, exit_px = "STOP", j, stop
            realized = (stop - entry_price) / risk * d
            tstop = elapsed
            break
        if hit_tgt:
            exit_type, exit_i, exit_px = "TARGET", j, target
            realized = 3.0 if signal_type in ("L", "S") else 2.5
            ttarget = elapsed
            break
        if elapsed >= max_bars:
            exit_type, exit_i, exit_px = "TIME", j, cl
            realized = (cl - entry_price) / risk * d
            break
    cr = cost_r(entry_price, stop, cost_mult)
    net = realized - cr
    wrong = _wrong_direction(mfe, mae, t05)
    return {
        "gross_R": realized,
        "net_R": net,
        "cost_R": cr,
        "MFE_R": mfe,
        "MAE_R": mae,
        "bars_to_MFE": bars_mfe,
        "bars_to_MAE": bars_mae,
        "bars_to_plus_0.5r": t05,
        "bars_to_plus_1r": t1,
        "bars_to_stop": tstop,
        "bars_to_target": ttarget,
        "exit_type": exit_type,
        "exit_timestamp": market.index[exit_i] if exit_i < len(market) else market.index[-1],
        "wrong_direction": int(wrong),
    }


def model_a_row(market: pd.DataFrame, pos: dict, sig, actionable_ts: pd.Timestamp) -> dict:
    """Phase44 current entry at 15m close (actionable time)."""
    # entry on last 1m bar of the 15m window ending at actionable
    entry_ts = actionable_ts - pd.Timedelta(minutes=1)
    entry_i = pos.get(entry_ts, -1)
    if entry_i < 0:
        entry_i = int(market.index.searchsorted(actionable_ts, side="left")) - 1
    if entry_i < 0:
        return {"filled": False}
    entry_px = float(sig.entry)
    sim = simulate_1m(market, entry_i, entry_px, float(sig.stop), float(sig.target), sig.direction, sig.signal_type)
    return {
        "filled": True,
        "entry_i": entry_i,
        "entry_price": entry_px,
        "entry_time": market.index[entry_i],
        "delay_min": 0.0,
        "model": "A",
        **sim,
    }
