"""Causal displacement features for every completed bar."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.indicators import add_base_indicators, true_range
from phase16.resample import cme_session_date

from .config import (
    ATR_DIAG,
    ATR_PRIMARY,
    PERCENTILE_MIN_PERIODS,
    PERCENTILE_WINDOW_BARS,
    SESSION_BUCKETS,
    STRUCTURE_LOOKBACK,
    VOLUME_MEDIAN_BARS,
)


def body_atr_bucket(value: float) -> str:
    if not np.isfinite(value):
        return "UNKNOWN"
    if value < 0.50:
        return "<0.50"
    if value < 0.75:
        return "0.50-0.75"
    if value < 1.00:
        return "0.75-1.00"
    if value < 1.25:
        return "1.00-1.25"
    if value < 1.50:
        return "1.25-1.50"
    return ">=1.50"


def session_bucket_label(timestamp: pd.Timestamp) -> str:
    minute = timestamp.hour * 60 + timestamp.minute
    for name, (start, end) in SESSION_BUCKETS.items():
        if start > end:
            if minute >= start or minute < end:
                return name
        elif start <= minute < end:
            return name
    return "OTHER"


def _wilder_atr(tr: pd.Series, length: int) -> pd.Series:
    return tr.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def _rolling_percentile(series: pd.Series) -> pd.Series:
    def rank_last(window: np.ndarray) -> float:
        current = window[-1]
        if not np.isfinite(current):
            return np.nan
        valid = window[np.isfinite(window)]
        if len(valid) < 50:
            return np.nan
        return float((valid <= current).mean())

    return series.astype(float).rolling(PERCENTILE_WINDOW_BARS, min_periods=PERCENTILE_MIN_PERIODS).apply(
        rank_last, raw=True
    )


def prepare_displacement_frame(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.sort_index().copy()
    data = add_base_indicators(data, config)
    tr = true_range(data)
    data["true_range"] = tr
    data["atr24"] = _wilder_atr(tr, ATR_PRIMARY)
    data["atr6"] = _wilder_atr(tr, ATR_DIAG[0])
    data["atr72"] = _wilder_atr(tr, ATR_DIAG[1])
    data["atr"] = data["atr24"]

    bar_range = data["high"] - data["low"]
    body = (data["close"] - data["open"]).abs()
    data["bar_range"] = bar_range
    data["body"] = body
    data["tr_atr24"] = tr / data["atr24"]
    data["range_atr24"] = bar_range / data["atr24"]
    data["body_atr24"] = body / data["atr24"]
    data["body_range"] = body / bar_range.replace(0, np.nan)
    data["return_atr24"] = (data["close"] - data["close"].shift(1)) / data["atr24"]

    bullish = data["close"] > data["open"]
    bearish = data["close"] < data["open"]
    clv = np.where(
        bullish,
        (data["close"] - data["low"]) / bar_range.replace(0, np.nan),
        np.where(bearish, (data["high"] - data["close"]) / bar_range.replace(0, np.nan), 0.5),
    )
    data["close_location"] = clv
    data["direction"] = np.where(bullish, "BULLISH", np.where(bearish, "BEARISH", "NEUTRAL"))

    data["volume_median24"] = data["volume"].rolling(VOLUME_MEDIAN_BARS, min_periods=VOLUME_MEDIAN_BARS).median()
    data["volume_ratio24"] = data["volume"] / data["volume_median24"]

    data["body_atr_pct"] = _rolling_percentile(data["body_atr24"])
    data["strength_bucket"] = data["body_atr24"].map(body_atr_bucket)

    prev_high = data["high"].shift(1).rolling(STRUCTURE_LOOKBACK, min_periods=STRUCTURE_LOOKBACK).max()
    prev_low = data["low"].shift(1).rolling(STRUCTURE_LOOKBACK, min_periods=STRUCTURE_LOOKBACK).min()
    data["prev_12_high"] = prev_high
    data["prev_12_low"] = prev_low
    data["structure_break"] = np.where(
        data["direction"] == "BULLISH",
        data["close"] > prev_high,
        np.where(data["direction"] == "BEARISH", data["close"] < prev_low, False),
    )

    same_dir = np.zeros(len(data), dtype=int)
    run = 0
    last = None
    for i, d in enumerate(data["direction"].to_numpy()):
        if d in {"BULLISH", "BEARISH"} and d == last:
            run += 1
        else:
            run = 1 if d in {"BULLISH", "BEARISH"} else 0
        same_dir[i] = run
        last = d
    data["directional_sequence_len"] = same_dir

    data["midpoint"] = (data["high"] + data["low"]) / 2.0
    data["return_3_atr"] = (data["close"] - data["close"].shift(3)) / data["atr24"]
    data["return_6_atr"] = (data["close"] - data["close"].shift(6)) / data["atr24"]
    data["distance_12_atr"] = (data["close"] - data["close"].shift(12)).abs() / data["atr24"]
    abs_rets = data["close"].diff().abs()
    path_12 = abs_rets.rolling(12, min_periods=12).sum()
    net_12 = (data["close"] - data["close"].shift(12)).abs()
    data["path_efficiency_12"] = net_12 / path_12.replace(0, np.nan)

    abs_ret = data["close"].diff().abs()
    data["accel_vs_3"] = abs_ret / abs_ret.shift(1).rolling(3, min_periods=3).mean()
    data["accel_vs_6"] = abs_ret / abs_ret.shift(1).rolling(6, min_periods=6).mean()

    data["cme_session_date"] = cme_session_date(data.index)
    data["session_bucket"] = [session_bucket_label(ts) for ts in data.index]
    return data
