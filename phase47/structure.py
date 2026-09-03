"""Causal 1m structure helpers for price-action features."""

from __future__ import annotations

import numpy as np
import pandas as pd


def causal_swing_levels(high: np.ndarray, low: np.ndarray, i: int) -> tuple[float, float, int, int]:
    """Return (swing_high, swing_low, swing_high_bar, swing_low_bar) using bars <= i."""
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


def structure_age_bars(i: int, swing_bar: int) -> float:
    if swing_bar < 0:
        return np.nan
    return float(i - swing_bar)


def liquidity_sweep_before(
    high: np.ndarray,
    low: np.ndarray,
    start_i: int,
    end_i: int,
    direction: str,
    swing_level: float,
    swing_bar: int,
) -> bool:
    """Test H: sweep of confirmed swing before B1 at end_i."""
    if swing_bar < 0 or not np.isfinite(swing_level) or end_i <= start_i:
        return False
    long = str(direction).lower() == "long"
    for j in range(max(start_i, swing_bar + 1), end_i + 1):
        if long and low[j] <= swing_level:
            return True
        if not long and high[j] >= swing_level:
            return True
    return False


def count_touches(high: np.ndarray, low: np.ndarray, level: float, start_i: int, end_i: int, *, long: bool) -> int:
    tol = max(abs(level) * 0.0001, 0.25)
    touches = 0
    for j in range(max(0, start_i), end_i + 1):
        if long and abs(low[j] - level) <= tol:
            touches += 1
        elif not long and abs(high[j] - level) <= tol:
            touches += 1
    return touches
