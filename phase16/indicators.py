"""Causal indicators and time/session helpers.

Every returned series is indexed at the bar where the value becomes knowable.
Confirmed pivots are therefore emitted on the confirmation bar, never on the
historical pivot bar.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from .config import FrozenConfig


def pine_sma(values: pd.Series, length: int) -> pd.Series:
    return values.astype(float).rolling(length, min_periods=length).mean()


def pine_ema(values: pd.Series, length: int) -> pd.Series:
    """Pine-compatible causal EMA seeded from the first non-NA observation."""
    return values.astype(float).ewm(alpha=2.0 / (length + 1.0), adjust=False).mean()


def pine_rma(values: pd.Series, length: int) -> pd.Series:
    """Wilder RMA with an SMA seed, matching ``ta.rma`` warm-up behavior."""
    source = values.astype(float).to_numpy()
    result = np.full(len(source), np.nan, dtype=float)
    valid = np.flatnonzero(~np.isnan(source))
    if len(valid) < length:
        return pd.Series(result, index=values.index, name=values.name)
    seed_end_pos = int(valid[length - 1])
    seed_values = source[valid[:length]]
    result[seed_end_pos] = float(np.mean(seed_values))
    previous = result[seed_end_pos]
    for pos in range(seed_end_pos + 1, len(source)):
        current = source[pos]
        if np.isnan(current):
            result[pos] = previous
        else:
            previous = (previous * (length - 1) + current) / length
            result[pos] = previous
    return pd.Series(result, index=values.index, name=values.name)


def true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1, skipna=True).rename("true_range")


def atr(frame: pd.DataFrame, length: int = 14) -> pd.Series:
    return pine_rma(true_range(frame), length).rename("atr")


def confirmed_pivots(
    values: pd.Series, left: int, right: int, kind: str
) -> pd.Series:
    """Return pivot prices on their right-side confirmation bars.

    The asymmetric comparisons reproduce Pine's right-most resolution for a
    flat plateau: a high is >= the left wing and > the right wing (inverse for
    lows). No value at position *i* depends on observations after *i*.
    """
    if kind not in {"high", "low"}:
        raise ValueError("kind must be 'high' or 'low'")
    source = values.astype(float).to_numpy()
    output = np.full(len(source), np.nan, dtype=float)
    for confirmed_at in range(left + right, len(source)):
        pivot_at = confirmed_at - right
        candidate = source[pivot_at]
        if np.isnan(candidate):
            continue
        left_values = source[pivot_at - left : pivot_at]
        right_values = source[pivot_at + 1 : confirmed_at + 1]
        if np.isnan(left_values).any() or np.isnan(right_values).any():
            continue
        if kind == "high":
            is_pivot = bool(
                np.all(candidate >= left_values) and np.all(candidate > right_values)
            )
        else:
            is_pivot = bool(
                np.all(candidate <= left_values) and np.all(candidate < right_values)
            )
        if is_pivot:
            output[confirmed_at] = candidate
    return pd.Series(output, index=values.index, name=f"pivot_{kind}")


def add_base_indicators(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    result = frame.copy()
    result["atr"] = atr(result, config.phase2_atr_length)
    result["body"] = (result["close"] - result["open"]).abs()
    result["body_sma"] = pine_sma(result["body"], config.se_displacement_lookback)
    result["structure_pivot_high"] = confirmed_pivots(
        result["high"], config.structure_left, config.structure_right, "high"
    )
    result["structure_pivot_low"] = confirmed_pivots(
        result["low"], config.structure_left, config.structure_right, "low"
    )
    result["liquidity_pivot_high"] = confirmed_pivots(
        result["high"], config.liquidity_left, config.liquidity_right, "high"
    )
    result["liquidity_pivot_low"] = confirmed_pivots(
        result["low"], config.liquidity_left, config.liquidity_right, "low"
    )
    return result


def session_bucket(timestamp: pd.Timestamp) -> int:
    """Return the frozen Pine session bucket for an exchange-local timestamp."""
    minute = timestamp.hour * 60 + timestamp.minute
    if minute >= 18 * 60 or minute < 4 * 60:
        return 0  # Overnight
    if minute < 9 * 60 + 30:
        return 1  # Premarket
    if minute < 10 * 60 + 30:
        return 2  # Opening hour
    if minute < 12 * 60:
        return 3  # Morning
    if minute < 14 * 60:
        return 4  # Midday
    if minute < 16 * 60:
        return 5  # Afternoon
    return 6  # After-hours maintenance/close window


def session_bucket_name(bucket: int) -> str:
    return {
        0: "Overnight",
        1: "Premarket",
        2: "Opening",
        3: "Morning",
        4: "Midday",
        5: "Afternoon",
        6: "After-hours",
    }.get(int(bucket), "Unknown")


def htf_regime_name(regime: int) -> str:
    return {1: "Bull", -1: "Bear", 0: "Neutral"}.get(int(regime), "Neutral")


def is_in_session(timestamp: pd.Timestamp, session: str) -> bool:
    """Evaluate TradingView-style HHMM-HHMM sessions in local exchange time."""
    start_text, end_text = session.split("-")
    start = int(start_text[:2]) * 60 + int(start_text[2:])
    end = int(end_text[:2]) * 60 + int(end_text[2:])
    current = timestamp.hour * 60 + timestamp.minute
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def add_previous_closed_htf_regime(
    frame: pd.DataFrame, config: FrozenConfig
) -> pd.DataFrame:
    """Attach the previous *closed* HTF regime without lookahead.

    Bars are expected to use opening timestamps. All chart bars within an HTF
    bucket receive values from the immediately preceding completed HTF bucket.
    """
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("frame must use a DatetimeIndex")
    rule = f"{config.htf_timeframe_minutes}min"
    htf = frame[["open", "high", "low", "close", "volume"]].resample(
        rule, label="left", closed="left", origin="start_day"
    ).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    htf = htf.dropna(subset=["open", "high", "low", "close"])
    fast = pine_ema(htf["close"], config.htf_fast_ema)
    slow = pine_ema(htf["close"], config.htf_slow_ema)
    htf_atr = atr(htf, config.htf_atr_length)

    previous_close = htf["close"].shift(1)
    previous_fast = fast.shift(1)
    previous_slow = slow.shift(1)
    fast_two_back = fast.shift(2)
    previous_atr = htf_atr.shift(1)
    wide = (previous_fast - previous_slow).abs() >= (
        config.htf_neutral_atr_threshold * previous_atr
    )
    bull = (
        wide
        & (previous_close > previous_fast)
        & (previous_fast > previous_slow)
        & (previous_fast > fast_two_back)
    )
    bear = (
        wide
        & (previous_close < previous_fast)
        & (previous_fast < previous_slow)
        & (previous_fast < fast_two_back)
    )
    regimes = pd.Series(
        np.where(bull, 1, np.where(bear, -1, 0)), index=htf.index, dtype=int
    )
    bucket = frame.index.floor(rule)
    mapping = regimes.to_dict()
    result = frame.copy()
    result["htf_regime"] = [int(mapping.get(key, 0)) for key in bucket]
    return result


def crt_reference_and_sweeps(frame: pd.DataFrame) -> pd.DataFrame:
    """Recreate the default chart-timeframe CRT reference and reclaim events."""
    result = pd.DataFrame(index=frame.index)
    result["crt_high"] = frame["high"].shift(1)
    result["crt_low"] = frame["low"].shift(1)
    result["sweep_above"] = (frame["high"] > result["crt_high"]) & (
        frame["close"] < result["crt_high"]
    )
    result["sweep_below"] = (frame["low"] < result["crt_low"]) & (
        frame["close"] > result["crt_low"]
    )
    return result


def score_band(score: float) -> str:
    if score < 70:
        return "<70"
    if score < 75:
        return "70-74"
    if score < 80:
        return "75-79"
    if score < 85:
        return "80-84"
    if score < 90:
        return "85-89"
    if score < 95:
        return "90-94"
    return "95+"


def finite_or(value: float, fallback: float) -> float:
    try:
        return float(value) if math.isfinite(float(value)) else fallback
    except (TypeError, ValueError):
        return fallback

