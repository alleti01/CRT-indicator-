"""Price-action variant filters and delayed-entry simulators."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.simulate import simulate_1m


def pass_break_strength(row: pd.Series, min_atr: float) -> bool:
    v = row.get("break_strength_atr", np.nan)
    return np.isfinite(v) and v >= min_atr


def pass_body_range(row: pd.Series, min_br: float) -> bool:
    v = row.get("body_range_ratio", np.nan)
    return np.isfinite(v) and v >= min_br


def pass_range_atr(row: pd.Series, min_ra: float) -> bool:
    v = row.get("range_atr", np.nan)
    return np.isfinite(v) and v >= min_ra


def pass_body_atr(row: pd.Series, min_ba: float) -> bool:
    v = row.get("body_atr", np.nan)
    return np.isfinite(v) and v >= min_ba


def pass_close_quality(row: pd.Series, min_cq: float) -> bool:
    v = row.get("close_quality", np.nan)
    return np.isfinite(v) and v >= min_cq


def pass_opposing_wick(row: pd.Series, max_wick: float) -> bool:
    v = row.get("opposing_wick_ratio", np.nan)
    return np.isfinite(v) and v <= max_wick


def pass_structure_touches(row: pd.Series, min_touches: int) -> bool:
    v = row.get("structure_touches", 0)
    return np.isfinite(v) and int(v) >= min_touches


def pass_structure_age(row: pd.Series, min_age: int) -> bool:
    v = row.get("structure_age_bars", np.nan)
    return np.isfinite(v) and v >= min_age


def pass_liquidity_sweep(row: pd.Series) -> bool:
    return bool(row.get("local_liquidity_sweep", 0))


def follow_through_entry(
    market: pd.DataFrame,
    bos_i: int,
    direction: str,
    variant: str,
    structure_level: float,
    stop: float,
    target: float,
    signal_type: str,
) -> tuple[bool, int, float]:
    """F1-F4: entry after next closed bar."""
    if bos_i + 1 >= len(market):
        return False, -1, np.nan
    nb = market.iloc[bos_i + 1]
    bb = market.iloc[bos_i]
    long = str(direction).lower() == "long"
    ncl = float(nb.close)
    bcl = float(bb.close)
    if variant == "F1":
        ok = (long and ncl > bcl) or (not long and ncl < bcl)
    elif variant == "F2":
        ok = (long and float(nb.high) > float(bb.high)) or (not long and float(nb.low) < float(bb.low))
    elif variant == "F3":
        ok = (long and ncl >= structure_level) or (not long and ncl <= structure_level) if np.isfinite(structure_level) else False
    elif variant == "F4":
        dist = abs(bcl - structure_level) if np.isfinite(structure_level) else 0
        ok = (long and ncl >= bcl - 0.5 * dist) or (not long and ncl <= bcl + 0.5 * dist)
    else:
        ok = False
    if ok:
        return True, bos_i + 1, ncl
    return False, -1, np.nan


def retest_entry(
    market: pd.DataFrame,
    bos_i: int,
    direction: str,
    structure_level: float,
    tol_atr: float,
    stop: float,
    target: float,
    signal_type: str,
    *,
    max_wait: int = 10,
) -> tuple[bool, int, float]:
    long = str(direction).lower() == "long"
    atr = float(market.iloc[bos_i].get("atr", 1.0))
    tol = tol_atr * atr
    for j in range(bos_i + 1, min(len(market), bos_i + 1 + max_wait)):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        if not np.isfinite(structure_level):
            continue
        if long and lo <= structure_level + tol and cl >= structure_level:
            return True, j, cl
        if not long and hi >= structure_level - tol and cl <= structure_level:
            return True, j, cl
    return False, -1, np.nan


def simulate_variant_entry(
    market: pd.DataFrame,
    entry_i: int,
    entry_px: float,
    stop: float,
    target: float,
    direction: str,
    signal_type: str,
) -> dict:
    return simulate_1m(market, entry_i, entry_px, stop, target, direction, signal_type)
