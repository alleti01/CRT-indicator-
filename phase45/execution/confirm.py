"""Causal 1m price confirmation rules B1–B4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from .config import SWING_LOOKBACK


@dataclass
class FillResult:
    filled: bool
    entry_i: int = -1
    entry_price: float = np.nan
    entry_time: pd.Timestamp | None = None
    rule: str = ""
    delay_min: float = np.nan
    bos_level: float = np.nan


def _dir_code(direction: str) -> int:
    return 1 if str(direction).lower() == "long" else -1


def _causal_swing_levels(high: np.ndarray, low: np.ndarray, i: int) -> tuple[float, float]:
    """Most recent confirmed swing high/low using only bars <= i."""
    sh = sl = np.nan
    if i < 2:
        return sh, sl
    for j in range(i, 1, -1):
        if high[j - 1] > high[j - 2] and high[j - 1] > high[j]:
            sh = float(high[j - 1])
            break
    for j in range(i, 1, -1):
        if low[j - 1] < low[j - 2] and low[j - 1] < low[j]:
            sl = float(low[j - 1])
            break
    return sh, sl


def _window_indices(pos: dict, start_ts: pd.Timestamp, end_ts: pd.Timestamp, idx) -> range:
    start_i = pos.get(start_ts, -1)
    end_i = pos.get(end_ts, -1)
    if start_i < 0:
        # first bar at or after start
        start_i = int(idx.searchsorted(start_ts, side="left"))
    if end_i < 0:
        end_i = int(idx.searchsorted(end_ts, side="right")) - 1
    if start_i < 0 or end_i < start_i:
        return range(0)
    return range(start_i, end_i + 1)


def confirm_b1(market: pd.DataFrame, pos: dict, start_ts: pd.Timestamp, window_min: int, direction: str) -> FillResult:
    d = _dir_code(direction)
    end_ts = start_ts + pd.Timedelta(minutes=window_min)
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values
    cl = market["close"].astype(float).values
    for i in _window_indices(pos, start_ts, end_ts, market.index):
        sh, sl = _causal_swing_levels(hi, lo, i)
        if d == 1 and np.isfinite(sh) and cl[i] > sh:
            ts = market.index[i]
            return FillResult(True, i, float(cl[i]), ts, "B1", (ts - start_ts).total_seconds() / 60, sh)
        if d == -1 and np.isfinite(sl) and cl[i] < sl:
            ts = market.index[i]
            return FillResult(True, i, float(cl[i]), ts, "B1", (ts - start_ts).total_seconds() / 60, sl)
    return FillResult(False)


def confirm_b2(market: pd.DataFrame, pos: dict, start_ts: pd.Timestamp, window_min: int, direction: str) -> FillResult:
    d = _dir_code(direction)
    end_ts = start_ts + pd.Timedelta(minutes=window_min)
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values
    cl = market["close"].astype(float).values
    pull = False
    for i in _window_indices(pos, start_ts, end_ts, market.index):
        sh, sl = _causal_swing_levels(hi, lo, i)
        if d == 1 and np.isfinite(sl) and lo[i] <= sl:
            pull = True
        if d == -1 and np.isfinite(sh) and hi[i] >= sh:
            pull = True
        if pull:
            if d == 1 and np.isfinite(sh) and cl[i] > sh:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B2", (ts - start_ts).total_seconds() / 60, sh)
            if d == -1 and np.isfinite(sl) and cl[i] < sl:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B2", (ts - start_ts).total_seconds() / 60, sl)
    return FillResult(False)


def confirm_b3(market: pd.DataFrame, pos: dict, start_ts: pd.Timestamp, window_min: int, direction: str) -> FillResult:
    d = _dir_code(direction)
    end_ts = start_ts + pd.Timedelta(minutes=window_min)
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values
    cl = market["close"].astype(float).values
    op = market["open"].astype(float).values
    rejected = False
    for i in _window_indices(pos, start_ts, end_ts, market.index):
        rng = hi[i] - lo[i]
        if rng > 0:
            loc = (cl[i] - lo[i]) / rng
            if d == 1 and loc <= 0.35 and cl[i] >= op[i]:
                rejected = True
            if d == -1 and loc >= 0.65 and cl[i] <= op[i]:
                rejected = True
        sh, sl = _causal_swing_levels(hi, lo, i)
        if rejected:
            if d == 1 and np.isfinite(sh) and cl[i] > sh:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B3", (ts - start_ts).total_seconds() / 60, sh)
            if d == -1 and np.isfinite(sl) and cl[i] < sl:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B3", (ts - start_ts).total_seconds() / 60, sl)
    return FillResult(False)


def confirm_b4(market: pd.DataFrame, pos: dict, start_ts: pd.Timestamp, window_min: int, direction: str) -> FillResult:
    d = _dir_code(direction)
    end_ts = start_ts + pd.Timedelta(minutes=window_min)
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values
    cl = market["close"].astype(float).values
    bos_level = np.nan
    bos_i = -1
    for i in _window_indices(pos, start_ts, end_ts, market.index):
        sh, sl = _causal_swing_levels(hi, lo, i)
        if not np.isfinite(bos_level):
            if d == 1 and np.isfinite(sh) and cl[i] > sh:
                bos_level, bos_i = sh, i
            elif d == -1 and np.isfinite(sl) and cl[i] < sl:
                bos_level, bos_i = sl, i
        elif i > bos_i:
            tol = max(abs(bos_level) * 0.0001, 0.25)
            if d == 1 and lo[i] <= bos_level + tol and cl[i] >= bos_level:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B4", (ts - start_ts).total_seconds() / 60, bos_level)
            if d == -1 and hi[i] >= bos_level - tol and cl[i] <= bos_level:
                ts = market.index[i]
                return FillResult(True, i, float(cl[i]), ts, "B4", (ts - start_ts).total_seconds() / 60, bos_level)
    return FillResult(False)


RULES = {
    "B1": confirm_b1,
    "B2": confirm_b2,
    "B3": confirm_b3,
    "B4": confirm_b4,
}


def try_all_confirmations(market: pd.DataFrame, pos: dict, start_ts: pd.Timestamp, window_min: int, direction: str) -> dict[str, FillResult]:
    return {k: fn(market, pos, start_ts, window_min, direction) for k, fn in RULES.items()}
