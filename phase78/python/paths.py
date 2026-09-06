"""Path metrics — index-based for speed."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PATH_HORIZONS, TARGET_R


def risk_points(entry: float, stop: float, direction: str) -> float:
    if direction == "LONG":
        return entry - stop
    return stop - entry


def symmetric_stop(entry: float, stop: float, direction: str) -> float:
    """Mirror stop distance for direction-control comparisons."""
    dist = abs(entry - stop)
    if dist <= 0 or not np.isfinite(dist):
        return stop
    return entry - dist if direction == "LONG" else entry + dist


def _slice_by_time(
    index: pd.DatetimeIndex,
    highs: np.ndarray,
    lows: np.ndarray,
    entry_time: pd.Timestamp,
    max_minutes: int,
) -> tuple[np.ndarray, np.ndarray]:
    start = int(index.searchsorted(entry_time))
    end = int(index.searchsorted(entry_time + pd.Timedelta(minutes=max_minutes), side="right"))
    return highs[start:end], lows[start:end]


def mfe_mae_arrays(
    index: pd.DatetimeIndex,
    highs: np.ndarray,
    lows: np.ndarray,
    entry_time: pd.Timestamp,
    entry_price: float,
    direction: str,
    horizons_min: tuple[int, ...] = PATH_HORIZONS,
) -> dict:
    out: dict = {}
    for hm in horizons_min:
        h, l = _slice_by_time(index, highs, lows, entry_time, hm)
        if h.size == 0:
            continue
        if direction == "LONG":
            out[f"mfe_{hm}m"] = float(h.max() - entry_price)
            out[f"mae_{hm}m"] = float(entry_price - l.min())
        else:
            out[f"mfe_{hm}m"] = float(entry_price - l.min())
            out[f"mae_{hm}m"] = float(h.max() - entry_price)
    return out


def first_passage_r_arrays(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_price: float,
    stop: float,
    direction: str,
    r_levels: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0),
) -> dict:
    r = risk_points(entry_price, stop, direction)
    if r <= 0 or not np.isfinite(r):
        return {f"plus_{lv}R_before_minus_1R": np.nan for lv in r_levels}
    out = {}
    for lv in r_levels:
        hit_plus = False
        hit_minus = False
        for hi, lo in zip(highs, lows):
            if direction == "LONG":
                if lo <= stop:
                    hit_minus = True
                if hi >= entry_price + lv * r:
                    hit_plus = True
            else:
                if hi >= stop:
                    hit_minus = True
                if lo <= entry_price - lv * r:
                    hit_plus = True
            if hit_plus and not hit_minus:
                out[f"plus_{lv}R_before_minus_1R"] = 1
                break
            if hit_minus:
                out[f"plus_{lv}R_before_minus_1R"] = 0
                break
        else:
            out[f"plus_{lv}R_before_minus_1R"] = 0
    return out


def simulate_trade_arrays(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_price: float,
    stop: float,
    direction: str,
    target_r: float,
) -> dict:
    r = risk_points(entry_price, stop, direction)
    if r <= 0:
        return {"outcome_r": np.nan, "exit_reason": "BAD_RISK"}
    target = entry_price + target_r * r if direction == "LONG" else entry_price - target_r * r
    for hi, lo in zip(highs, lows):
        stop_hit = lo <= stop if direction == "LONG" else hi >= stop
        tgt_hit = hi >= target if direction == "LONG" else lo <= target
        if stop_hit:
            return {"outcome_r": -1.0, "exit_reason": "STOP"}
        if tgt_hit:
            return {"outcome_r": target_r, "exit_reason": "TARGET"}
    return {"outcome_r": 0.0, "exit_reason": "TIME"}


def batch_paths(
    df: pd.DataFrame,
    entries: pd.DataFrame,
    target_r: float = TARGET_R[0],
) -> pd.DataFrame:
    index = df.index
    highs = df["high"].values
    lows = df["low"].values
    rows = []
    for _, e in entries.iterrows():
        et = e["entry_time"]
        ep, stop, d = e["entry_price"], e["stop"], e["direction"]
        h60, l60 = _slice_by_time(index, highs, lows, et, 60)
        sim = simulate_trade_arrays(h60, l60, ep, stop, d, target_r)
        row = dict(e)
        row.update(sim)
        row.update(mfe_mae_arrays(index, highs, lows, et, ep, d))
        row.update(first_passage_r_arrays(h60, l60, ep, stop, d))
        rows.append(row)
    return pd.DataFrame(rows)
