"""Precompute immutable causal primitives — extract arrays once."""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase53.research.data import align_htf_to_1m, htf_bar_index, load_markets


@dataclass
class MarketArrays:
    """All immutable precomputed arrays for sequential bar processing."""
    hi: np.ndarray
    lo: np.ndarray
    cl: np.ndarray
    op: np.ndarray
    atr: np.ndarray
    n: int
    idx: pd.DatetimeIndex
    # Causal swings
    sh: np.ndarray       # last confirmed swing high
    sl: np.ndarray       # last confirmed swing low
    sh1: np.ndarray      # most recent swing high
    sh2: np.ndarray      # second most recent swing high
    sl1: np.ndarray      # most recent swing low
    sl2: np.ndarray      # second most recent swing low
    # HTF
    m5_cl: np.ndarray
    m5_op: np.ndarray
    m5_hi: np.ndarray
    m5_lo: np.ndarray
    m5_atr: np.ndarray
    m5_idx: np.ndarray   # htf_bar_index mapping
    m15_cl: np.ndarray
    m15_op: np.ndarray
    m15_hi: np.ndarray
    m15_lo: np.ndarray
    m15_atr: np.ndarray
    m15_idx: np.ndarray
    # Derived
    body: np.ndarray
    avg_body: np.ndarray


def build_market_arrays(swing: int = 5) -> MarketArrays:
    """Load data and precompute everything once."""
    m1, m5, m15 = load_markets()
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)

    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    body = np.abs(cl - op)
    avg_body = pd.Series(body).rolling(20, min_periods=1).mean().values

    _sh1, _sh2 = precompute_last2_swing_highs(hi, swing)
    _sl1, _sl2 = precompute_last2_swing_lows(lo, swing)
    return MarketArrays(
        hi=hi, lo=lo, cl=cl, op=op, atr=atr, n=len(m1), idx=m1.index,
        sh=precompute_swing_highs(hi, swing),
        sl=precompute_swing_lows(lo, swing),
        sh1=_sh1, sh2=_sh2, sl1=_sl1, sl2=_sl2,
        m5_cl=m5a["close"].values.astype(float),
        m5_op=m5a["open"].values.astype(float),
        m5_hi=m5a["high"].values.astype(float),
        m5_lo=m5a["low"].values.astype(float),
        m5_atr=m5a["atr"].values.astype(float) if "atr" in m5a.columns else np.full(len(m5a), np.nan),
        m5_idx=htf_bar_index(m1.index, m5.index),
        m15_cl=m15a["close"].values.astype(float),
        m15_op=m15a["open"].values.astype(float),
        m15_hi=m15a["high"].values.astype(float),
        m15_lo=m15a["low"].values.astype(float),
        m15_atr=m15a["atr"].values.astype(float) if "atr" in m15a.columns else np.full(len(m15a), np.nan),
        m15_idx=htf_bar_index(m1.index, m15.index),
        body=body, avg_body=avg_body,
    )
