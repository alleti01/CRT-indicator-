"""Minimal independent trade simulator — intentionally separate from Phase58I."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class SimResult:
    entry_i: int
    entry_price: float
    stop: float
    target: float
    exit_i: int
    exit_price: float
    exit_reason: str
    gross_r: float
    mfe_r: float
    mae_r: float
    risk_pts: float
    atr: float
    collision_bar: bool = False


def entry_atr(atr_series: np.ndarray, entry_i: int) -> float:
    v = float(atr_series[entry_i])
    if np.isfinite(v) and v > 0:
        return v
    for k in range(max(0, entry_i - 5), entry_i + 1):
        if np.isfinite(atr_series[k]) and atr_series[k] > 0:
            return float(atr_series[k])
    return 1.0


def init_levels(direction: str, entry_price: float, atr: float, stop_atr: float, target_r: float) -> tuple[float, float, float]:
    risk_pts = stop_atr * atr
    if direction == "LONG":
        stop = entry_price - risk_pts
        target = entry_price + target_r * risk_pts
    else:
        stop = entry_price + risk_pts
        target = entry_price - target_r * risk_pts
    return stop, target, risk_pts


def simulate_bar_path(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    entry_i: int,
    direction: str,
    entry_price: float,
    stop_atr: float,
    atr_series: np.ndarray,
    target_r: float = 2.5,
    max_hold_min: int = 60,
) -> SimResult:
    """Walk 1M bars after entry; stop-before-target on same bar."""
    atr = entry_atr(atr_series, entry_i)
    stop, target, risk_pts = init_levels(direction, entry_price, atr, stop_atr, target_r)
    if risk_pts <= 0:
        risk_pts = 1e-9

    sign = 1.0 if direction == "LONG" else -1.0
    deadline = min(len(cl) - 1, entry_i + max_hold_min)
    mfe = mae = 0.0
    collision = False

    for i in range(entry_i + 1, deadline + 1):
        bar_h, bar_l = float(hi[i]), float(lo[i])
        if direction == "LONG":
            mfe = max(mfe, (bar_h - entry_price) / risk_pts)
            mae = max(mae, (entry_price - bar_l) / risk_pts)
            hit_stop = bar_l <= stop
            hit_target = bar_h >= target
        else:
            mfe = max(mfe, (entry_price - bar_l) / risk_pts)
            mae = max(mae, (bar_h - entry_price) / risk_pts)
            hit_stop = bar_h >= stop
            hit_target = bar_l <= target

        if hit_stop and hit_target:
            collision = True
        if hit_stop:
            return SimResult(entry_i, entry_price, stop, target, i, stop, "STOP", -1.0, mfe, mae, risk_pts, atr, collision)
        if hit_target:
            return SimResult(entry_i, entry_price, stop, target, i, target, "TARGET", target_r, mfe, mae, risk_pts, atr, collision)

    exit_i = deadline
    exit_price = float(cl[exit_i])
    realized = sign * (exit_price - entry_price) / risk_pts
    return SimResult(entry_i, entry_price, stop, target, exit_i, exit_price, "TIME", realized, mfe, mae, risk_pts, atr, False)


def simulate_batch(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    atr: np.ndarray,
    trades: list[dict],
    stop_atr: float,
    target_r: float = 2.5,
    max_hold_min: int = 60,
) -> list[SimResult]:
    out = []
    for t in trades:
        out.append(simulate_bar_path(
            hi, lo, cl,
            int(t["entry_i"]),
            t["direction"],
            float(t["entry_price"]),
            stop_atr,
            atr,
            target_r,
            max_hold_min,
        ))
    return out
