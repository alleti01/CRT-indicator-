"""Bar-path analysis for management forensics (evaluation labels may use future path)."""
from __future__ import annotations

import numpy as np

from phase58b.research.precompute import MTFArrays


def _risk_pts(entry_price: float, stop: float) -> float:
    r = abs(entry_price - stop)
    return r if r > 1e-9 else 1e-9


def path_excursions(
    m: MTFArrays,
    entry_i: int,
    exit_i: int,
    direction: str,
    entry_price: float,
    risk_pts: float,
) -> dict:
    """MFE/MAE from entry through exit_i inclusive."""
    d = 1 if direction == "LONG" else -1
    mfe = mae = 0.0
    end = min(exit_i, m.m1_n - 1)
    for i in range(entry_i + 1, end + 1):
        h, l = m.m1_hi[i], m.m1_lo[i]
        if d == 1:
            mfe = max(mfe, (h - entry_price) / risk_pts)
            mae = max(mae, (entry_price - l) / risk_pts)
        else:
            mfe = max(mfe, (entry_price - l) / risk_pts)
            mae = max(mae, (h - entry_price) / risk_pts)
    return {"mfe_r": mfe, "mae_r": mae}


def post_exit_excursion(
    m: MTFArrays,
    entry_i: int,
    exit_i: int,
    direction: str,
    entry_price: float,
    risk_pts: float,
    horizon_min: int,
) -> float:
    """Max favorable R from original entry after exit_i for horizon minutes."""
    d = 1 if direction == "LONG" else -1
    end = min(m.m1_n - 1, exit_i + horizon_min)
    best = 0.0
    for i in range(exit_i + 1, end + 1):
        h, l = m.m1_hi[i], m.m1_lo[i]
        if d == 1:
            best = max(best, (h - entry_price) / risk_pts)
        else:
            best = max(best, (entry_price - l) / risk_pts)
    return best


def time_to_threshold(
    m: MTFArrays,
    entry_i: int,
    direction: str,
    entry_price: float,
    risk_pts: float,
    threshold_r: float,
    max_bars: int = 120,
) -> int | None:
    d = 1 if direction == "LONG" else -1
    end = min(m.m1_n - 1, entry_i + max_bars)
    for i in range(entry_i + 1, end + 1):
        h, l = m.m1_hi[i], m.m1_lo[i]
        fav = (h - entry_price) / risk_pts if d == 1 else (entry_price - l) / risk_pts
        if fav >= threshold_r:
            return i - entry_i
    return None


def mae_before_threshold(
    m: MTFArrays,
    entry_i: int,
    direction: str,
    entry_price: float,
    risk_pts: float,
    threshold_r: float,
    max_bars: int = 120,
) -> float:
    """Max adverse excursion before first reaching threshold_r (winners)."""
    d = 1 if direction == "LONG" else -1
    end = min(m.m1_n - 1, entry_i + max_bars)
    mae = 0.0
    for i in range(entry_i + 1, end + 1):
        h, l = m.m1_hi[i], m.m1_lo[i]
        adv = (entry_price - l) / risk_pts if d == 1 else (h - entry_price) / risk_pts
        mae = max(mae, adv)
        fav = (h - entry_price) / risk_pts if d == 1 else (entry_price - l) / risk_pts
        if fav >= threshold_r:
            break
    return mae
