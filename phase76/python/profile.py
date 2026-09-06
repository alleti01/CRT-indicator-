"""Volume profile from 1m bars — BAR_APPROX_PROFILE only at LEVEL 0."""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from .config import PROFILE_BIN_SIZE, VALUE_AREA_PCT


def poc_vah_val_from_hist(histogram: Dict[int, float]) -> Tuple[float, float, float]:
    """POC + 70% value area from integer bin histogram."""
    if not histogram:
        return np.nan, np.nan, np.nan
    bins = sorted(histogram.keys())
    vols = np.array([histogram[b] for b in bins], dtype=float)
    total = vols.sum()
    if total <= 0:
        return np.nan, np.nan, np.nan
    poc_idx = int(np.argmax(vols))
    poc = (bins[poc_idx] + 0.5) * PROFILE_BIN_SIZE

    # Expand from POC until VALUE_AREA_PCT of volume captured
    lo_i, hi_i = poc_idx, poc_idx
    captured = vols[poc_idx]
    while captured / total < VALUE_AREA_PCT and (lo_i > 0 or hi_i < len(bins) - 1):
        vol_below = vols[lo_i - 1] if lo_i > 0 else -1.0
        vol_above = vols[hi_i + 1] if hi_i < len(bins) - 1 else -1.0
        if vol_below >= vol_above and lo_i > 0:
            lo_i -= 1
            captured += vols[lo_i]
        elif hi_i < len(bins) - 1:
            hi_i += 1
            captured += vols[hi_i]
        elif lo_i > 0:
            lo_i -= 1
            captured += vols[lo_i]
        else:
            break

    val = (bins[lo_i] + 0.5) * PROFILE_BIN_SIZE
    vah = (bins[hi_i] + 0.5) * PROFILE_BIN_SIZE
    return poc, vah, val


def hvn_lvn_bins(histogram: Dict[int, float], *, hvn_pct: float, lvn_pct: float) -> tuple[set[int], set[int]]:
    """Causal HVN/LVN bin sets from current histogram (not future)."""
    if len(histogram) < 3:
        return set(), set()
    vols = np.array(list(histogram.values()), dtype=float)
    positive = vols[vols > 0]
    if len(positive) < 3:
        return set(), set()
    hvn_cut = np.quantile(positive, hvn_pct)
    lvn_cut = np.quantile(positive, lvn_pct)
    hvn = {b for b, v in histogram.items() if v >= hvn_cut}
    lvn = {b for b, v in histogram.items() if v <= lvn_cut and v > 0}
    return hvn, lvn


def price_in_bins(price: float, bins: set[int], bin_size: float) -> bool:
    if not bins:
        return False
    b = int(np.floor(price / bin_size))
    return b in bins
