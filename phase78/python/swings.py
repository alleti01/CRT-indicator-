"""Causal swing highs/lows — integer indices for speed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PIVOT_LEFT, PIVOT_RIGHT

Swing = tuple[int, float, int]  # pivot_idx, price, confirm_idx


def causal_pivot_highs_lows(
    high: np.ndarray,
    low: np.ndarray,
    left: int = PIVOT_LEFT,
    right: int = PIVOT_RIGHT,
) -> tuple[list[Swing], list[Swing]]:
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    n = len(high)
    sh: list[Swing] = []
    sl: list[Swing] = []
    for conf_i in range(left + right, n):
        pivot = conf_i - right
        start = pivot - left
        end = pivot + right + 1
        win_h = high[start:end]
        win_l = low[start:end]
        hp = high[pivot]
        lp = low[pivot]
        if hp >= win_h.max() and np.sum(win_h == hp) == 1:
            sh.append((pivot, float(hp), conf_i))
        if lp <= win_l.min() and np.sum(win_l == lp) == 1:
            sl.append((pivot, float(lp), conf_i))
    return sh, sl


def swings_to_timestamps(
    swings: list[Swing], index: pd.DatetimeIndex
) -> list[tuple[int, float, pd.Timestamp]]:
    return [(p, px, index[c]) for p, px, c in swings]
