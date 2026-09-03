"""Causal swing detection — no future pivots."""

from __future__ import annotations

import numpy as np


def precompute_swing_highs(high: np.ndarray, swing: int = 5) -> np.ndarray:
    n = len(high)
    out = np.full(n, np.nan)
    last = np.nan
    for i in range(n):
        j = i - swing
        if j >= swing:
            window = high[j - swing : j + swing + 1]
            if high[j] == np.max(window):
                last = float(high[j])
        out[i] = last
    return out


def precompute_swing_lows(low: np.ndarray, swing: int = 5) -> np.ndarray:
    n = len(low)
    out = np.full(n, np.nan)
    last = np.nan
    for i in range(n):
        j = i - swing
        if j >= swing:
            window = low[j - swing : j + swing + 1]
            if low[j] == np.min(window):
                last = float(low[j])
        out[i] = last
    return out


def precompute_last2_swing_highs(high: np.ndarray, swing: int = 5) -> tuple[np.ndarray, np.ndarray]:
    n = len(high)
    h1 = np.full(n, np.nan)
    h2 = np.full(n, np.nan)
    pivots: list[float] = []
    for i in range(n):
        j = i - swing
        if j >= swing:
            window = high[j - swing : j + swing + 1]
            if high[j] == np.max(window):
                pivots.append(float(high[j]))
        if pivots:
            h1[i] = pivots[-1]
        if len(pivots) >= 2:
            h2[i] = pivots[-2]
    return h1, h2


def precompute_last2_swing_lows(low: np.ndarray, swing: int = 5) -> tuple[np.ndarray, np.ndarray]:
    n = len(low)
    l1 = np.full(n, np.nan)
    l2 = np.full(n, np.nan)
    pivots: list[float] = []
    for i in range(n):
        j = i - swing
        if j >= swing:
            window = low[j - swing : j + swing + 1]
            if low[j] == np.min(window):
                pivots.append(float(low[j]))
        if pivots:
            l1[i] = pivots[-1]
        if len(pivots) >= 2:
            l2[i] = pivots[-2]
    return l1, l2


def causal_swing_high_idx(high: np.ndarray, i: int, swing: int = 5, lookback: int = 500) -> int:
    """Most recent confirmed swing high at or before i.

    Pivot at bar j is confirmed only once j+swing <= i (causal confirmation lag).
    """
    if i < swing * 2:
        return -1
    lo = max(swing, i - lookback)
    for j in range(i - swing, lo - 1, -1):
        if j - swing < 0:
            continue
        window = high[j - swing : j + swing + 1]
        if high[j] == np.max(window):
            return j
    return -1


def causal_swing_low_idx(low: np.ndarray, i: int, swing: int = 5, lookback: int = 500) -> int:
    if i < swing * 2:
        return -1
    lo = max(swing, i - lookback)
    for j in range(i - swing, lo - 1, -1):
        if j - swing < 0:
            continue
        window = low[j - swing : j + swing + 1]
        if low[j] == np.min(window):
            return j
    return -1


def causal_swing_high(high: np.ndarray, i: int, swing: int = 5) -> float:
    j = causal_swing_high_idx(high, i, swing)
    return float(high[j]) if j >= 0 else np.nan


def causal_swing_low(low: np.ndarray, i: int, swing: int = 5) -> float:
    j = causal_swing_low_idx(low, i, swing)
    return float(low[j]) if j >= 0 else np.nan


def recent_swing_highs(high: np.ndarray, i: int, n: int = 2, swing: int = 5) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    cur = i
    for _ in range(n):
        j = causal_swing_high_idx(high, cur, swing)
        if j < 0:
            break
        out.append((j, float(high[j])))
        cur = j - 1
    return out


def recent_swing_lows(low: np.ndarray, i: int, n: int = 2, swing: int = 5) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    cur = i
    for _ in range(n):
        j = causal_swing_low_idx(low, cur, swing)
        if j < 0:
            break
        out.append((j, float(low[j])))
        cur = j - 1
    return out
