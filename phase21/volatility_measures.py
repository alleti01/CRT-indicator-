"""Causal volatility measures and state classification."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.indicators import atr as atr_series, true_range
from phase16.resample import cme_session_date

from .config import (
    HIGH_PERCENTILE,
    LONG_BARS,
    LOW_PERCENTILE,
    MEDIUM_BARS,
    PERCENTILE_MIN_PERIODS,
    PERCENTILE_WINDOW_BARS,
    PRIMARY_STATE_MEASURE,
    SHORT_BARS,
)


def _wilder_atr(tr: pd.Series, length: int) -> pd.Series:
    return tr.ewm(alpha=1.0 / length, adjust=False, min_periods=length).mean()


def _rolling_percentile(series: pd.Series) -> pd.Series:
    values = series.astype(float)

    def rank_last(window: np.ndarray) -> float:
        current = window[-1]
        if not np.isfinite(current):
            return np.nan
        valid = window[np.isfinite(window)]
        if len(valid) < 50:
            return np.nan
        return float((valid <= current).mean())

    return values.rolling(PERCENTILE_WINDOW_BARS, min_periods=PERCENTILE_MIN_PERIODS).apply(
        rank_last, raw=True
    )


def _state_label(percentile: float) -> str:
    if not np.isfinite(percentile):
        return "UNKNOWN"
    if percentile <= LOW_PERCENTILE:
        return "LOW"
    if percentile >= HIGH_PERCENTILE:
        return "HIGH"
    return "NORMAL"


def _duration_bin(duration: int) -> str:
    if duration <= 3:
        return "1-3"
    if duration <= 6:
        return "4-6"
    if duration <= 12:
        return "7-12"
    if duration <= 24:
        return "13-24"
    return "25+"


def _shock_bin(percentile: float) -> str:
    if not np.isfinite(percentile):
        return "UNKNOWN"
    if percentile < 0.80:
        return "<80"
    if percentile < 0.90:
        return "80-90"
    if percentile < 0.95:
        return "90-95"
    if percentile < 0.99:
        return "95-99"
    return "99+"


def time_bucket_label(timestamp: pd.Timestamp) -> str:
    minute = timestamp.hour * 60 + timestamp.minute
    if minute >= 18 * 60 or minute < 4 * 60:
        return "OVERNIGHT"
    if minute < 9 * 60 + 30:
        return "PREMARKET"
    if minute < 10 * 60 + 30:
        return "RTH_OPEN"
    if minute < 12 * 60:
        return "RTH_MID_MORNING"
    if minute < 14 * 60:
        return "MIDDAY"
    if minute < 16 * 60:
        return "RTH_AFTERNOON"
    return "OTHER"


def transition_direction(open_price: float, close: float) -> str:
    if close > open_price:
        return "UP"
    if close < open_price:
        return "DOWN"
    return "NEUTRAL"


def prepare_volatility_frame(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.sort_index().copy()
    tr = true_range(data)
    data["true_range"] = tr
    data["bar_range"] = data["high"] - data["low"]
    data["atr_6"] = _wilder_atr(tr, SHORT_BARS)
    data["atr_24"] = _wilder_atr(tr, MEDIUM_BARS)
    data["atr_72"] = _wilder_atr(tr, LONG_BARS)
    data["atr"] = data["atr_24"]
    data["range_atr"] = data["bar_range"] / data["atr_24"]
    data["tr_atr"] = data["true_range"] / data["atr_24"]
    data["returns"] = data["close"].pct_change()
    data["abs_returns"] = data["returns"].abs()
    data["rv_6"] = data["returns"].rolling(SHORT_BARS, min_periods=SHORT_BARS).std()
    data["rv_24"] = data["returns"].rolling(MEDIUM_BARS, min_periods=MEDIUM_BARS).std()
    data["rv_72"] = data["returns"].rolling(LONG_BARS, min_periods=LONG_BARS).std()
    data["avg_range_6"] = data["bar_range"].rolling(SHORT_BARS, min_periods=SHORT_BARS).mean()
    data["avg_range_72"] = data["bar_range"].rolling(LONG_BARS, min_periods=LONG_BARS).mean()
    data["atr_ratio"] = data["atr_6"] / data["atr_72"]
    data["rv_ratio"] = data["rv_6"] / data["rv_72"]
    data["range_ratio"] = data["avg_range_6"] / data["avg_range_72"]
    data["range_over_median"] = data["bar_range"] / data["bar_range"].rolling(
        MEDIUM_BARS, min_periods=MEDIUM_BARS
    ).median()
    data["abs_return_over_rv"] = data["abs_returns"] / data["rv_6"]

    measure_map = {
        "ATR_RATIO": "atr_ratio",
        "RV_RATIO": "rv_ratio",
        "RANGE_RATIO": "range_ratio",
        "ATR_24": "atr_24",
    }
    for name, column in measure_map.items():
        pct = _rolling_percentile(data[column])
        data[f"pct_{name}"] = pct
        data[f"state_{name}"] = pct.map(_state_label)

    data["shock_score"] = data[["tr_atr", "range_over_median", "abs_return_over_rv"]].max(axis=1)
    data["shock_pct"] = _rolling_percentile(data["shock_score"])
    data["shock_bin"] = data["shock_pct"].map(_shock_bin)
    data["primary_state"] = data[f"state_{PRIMARY_STATE_MEASURE}"]
    data["primary_pct"] = data[f"pct_{PRIMARY_STATE_MEASURE}"]
    data["cme_session_date"] = cme_session_date(data.index)
    data["time_bucket"] = [time_bucket_label(ts) for ts in data.index]
    data["transition_direction"] = [
        transition_direction(float(o), float(c)) for o, c in zip(data["open"], data["close"])
    ]
    return data


def compression_duration_bins(states: pd.Series) -> pd.Series:
    durations = np.zeros(len(states), dtype=int)
    out = np.array(["0"] * len(states), dtype=object)
    run = 0
    for i, state in enumerate(states):
        if state == "LOW":
            run += 1
            durations[i] = run
            out[i] = _duration_bin(run)
        else:
            run = 0
            out[i] = "0"
    return pd.Series(out, index=states.index)
