"""Causal 1m structure helpers."""

from __future__ import annotations

import numpy as np


def causal_swing_levels(high: np.ndarray, low: np.ndarray, i: int) -> tuple[float, float, int, int]:
    sh = sl = np.nan
    sh_i = sl_i = -1
    if i < 2:
        return sh, sl, sh_i, sl_i
    for j in range(i, 1, -1):
        if high[j - 1] > high[j - 2] and high[j - 1] > high[j]:
            sh, sh_i = float(high[j - 1]), j - 1
            break
    for j in range(i, 1, -1):
        if low[j - 1] < low[j - 2] and low[j - 1] < low[j]:
            sl, sl_i = float(low[j - 1]), j - 1
            break
    return sh, sl, sh_i, sl_i


def opposite_bos(high: np.ndarray, low: np.ndarray, close: np.ndarray, i: int, direction: str) -> bool:
    """True if bar i confirms opposite-direction micro-BOS (B1-style)."""
    long = str(direction).lower() == "long"
    sh, sl, _, _ = causal_swing_levels(high, low, i)
    if long and np.isfinite(sl) and close[i] < sl:
        return True
    if not long and np.isfinite(sh) and close[i] > sh:
        return True
    return False


def trail_swing_stop(high: np.ndarray, low: np.ndarray, i: int, direction: str) -> float:
    """TR2: most recent confirmed swing (higher low for long, lower high for short)."""
    long = str(direction).lower() == "long"
    if long:
        for j in range(i, 1, -1):
            if low[j - 1] < low[j - 2] and low[j - 1] < low[j]:
                return float(low[j - 1])
        return np.nan
    for j in range(i, 1, -1):
        if high[j - 1] > high[j - 2] and high[j - 1] > high[j]:
            return float(high[j - 1])
    return np.nan
