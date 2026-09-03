"""Forward return measurement from event bar close."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import HORIZONS


def _continuation_sign(row: pd.Series, level_value: float, data: pd.DataFrame) -> int:
    idx = int(row.bar_index)
    bar = data.iloc[idx]
    close = float(bar.close)
    high = float(bar.high)
    low = float(bar.low)
    if high > level_value and close < level_value:
        return -1
    if low < level_value and close > level_value:
        return 1
    if close >= level_value:
        return 1
    return -1


def compute_event_forward(data: pd.DataFrame, row: pd.Series) -> dict:
    metrics: dict = {}
    idx = int(row.bar_index)
    if idx >= len(data) - 1:
        return metrics
    atr = float(row.atr) if np.isfinite(row.atr) and row.atr > 0 else np.nan
    if not np.isfinite(atr) or atr <= 0:
        return metrics
    event_close = float(row.close)
    level_side = str(row.level_side)
    level_value = float(row.level_value) if np.isfinite(row.level_value) else float("nan")
    highs = data["high"].to_numpy(dtype=float)
    lows = data["low"].to_numpy(dtype=float)
    closes = data["close"].to_numpy(dtype=float)

    for horizon in HORIZONS:
        end_idx = min(idx + horizon, len(data) - 1)
        if end_idx <= idx:
            continue
        window_high = float(highs[idx + 1 : end_idx + 1].max())
        window_low = float(lows[idx + 1 : end_idx + 1].min())
        end_close = float(closes[end_idx])
        raw_points = end_close - event_close
        up_atr = raw_points / atr
        down_atr = -raw_points / atr
        metrics[f"raw_points_{horizon}"] = raw_points
        metrics[f"atr_return_{horizon}"] = up_atr
        if level_side == "upper":
            cont = up_atr
            rev = down_atr
            mfe = (window_high - event_close) / atr
            mae = (event_close - window_low) / atr
        elif level_side == "lower":
            cont = down_atr
            rev = up_atr
            mfe = (event_close - window_low) / atr
            mae = (window_high - event_close) / atr
        else:
            sign = _continuation_sign(row, level_value, data)
            cont = up_atr if sign > 0 else down_atr
            rev = down_atr if sign > 0 else up_atr
            if sign > 0:
                mfe = (window_high - event_close) / atr
                mae = (event_close - window_low) / atr
            else:
                mfe = (event_close - window_low) / atr
                mae = (window_high - event_close) / atr
        metrics[f"continuation_atr_{horizon}"] = cont
        metrics[f"reversal_atr_{horizon}"] = rev
        metrics[f"mfe_atr_{horizon}"] = mfe
        metrics[f"mae_atr_{horizon}"] = mae
    return metrics


def attach_forward_returns(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, event in events.iterrows():
        payload = event.to_dict()
        payload.update(compute_event_forward(data, event))
        rows.append(payload)
    return pd.DataFrame(rows)


def recompute_forward_columns(data: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    base_cols = [
        c
        for c in events.columns
        if not any(
            c.startswith(prefix)
            for prefix in (
                "raw_points_",
                "atr_return_",
                "continuation_atr_",
                "reversal_atr_",
                "mfe_atr_",
                "mae_atr_",
            )
        )
    ]
    base = events[base_cols].copy()
    return attach_forward_returns(data, base)
