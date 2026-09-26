"""Exploratory causal candidate — visual hypothesis, not a fitted CDX clone."""
from __future__ import annotations

import pandas as pd


def apply_candidate_v1(feat: pd.DataFrame, *, cooldown: int = 8) -> pd.Series:
    """
    Family: local-extreme rejection.

    LONG: near 20-bar low, lower-wick rejection, bullish close.
    SHORT: near 20-bar high, upper-wick rejection, bearish close.
    Same-direction cooldown. Opposite signal resets.
    """
    long_trig = (
        (feat.get("near_low_20", 0) == 1)
        & (feat["lower_wick_frac"] >= 0.35)
        & (feat["bullish"] == 1)
        & (feat["close_loc"] >= 0.55)
    )
    short_trig = (
        (feat.get("near_high_20", 0) == 1)
        & (feat["upper_wick_frac"] >= 0.35)
        & (feat["bearish"] == 1)
        & (feat["close_loc"] <= 0.45)
    )
    out = pd.Series(0, index=feat.index, dtype=int)
    last_bar = -10_000
    last_dir = 0
    for i, (is_long, is_short) in enumerate(zip(long_trig.fillna(False), short_trig.fillna(False))):
        if is_long:
            if last_dir == 1 and (i - last_bar) < cooldown:
                continue
            out.iloc[i] = 1
            last_bar = i
            last_dir = 1
        elif is_short:
            if last_dir == -1 and (i - last_bar) < cooldown:
                continue
            out.iloc[i] = -1
            last_bar = i
            last_dir = -1
    return out
