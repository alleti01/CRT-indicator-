"""MTF precompute — 5M decision arrays, 15M context, 1M execution mapping."""
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
class MTFArrays:
    """Immutable arrays for 15M→5M→1M pipeline."""

    # 1M execution layer
    m1_hi: np.ndarray
    m1_lo: np.ndarray
    m1_cl: np.ndarray
    m1_op: np.ndarray
    m1_atr: np.ndarray
    m1_n: int
    m1_idx: pd.DatetimeIndex

    # 5M decision layer (native)
    m5_hi: np.ndarray
    m5_lo: np.ndarray
    m5_cl: np.ndarray
    m5_op: np.ndarray
    m5_atr: np.ndarray
    m5_n: int
    m5_idx: pd.DatetimeIndex
    m5_sh: np.ndarray
    m5_sl: np.ndarray
    m5_sh1: np.ndarray
    m5_sh2: np.ndarray
    m5_sl1: np.ndarray
    m5_sl2: np.ndarray
    m5_body: np.ndarray

    # 15M context aligned to 5M (last completed bar)
    m15_cl: np.ndarray
    m15_op: np.ndarray
    m15_hi: np.ndarray
    m15_lo: np.ndarray
    m15_atr: np.ndarray
    m15_idx_on_m5: np.ndarray

    # Cross-TF mapping
    m1_to_m5: np.ndarray          # 5M bar index for each 1M bar
    m5_close_m1_i: np.ndarray     # first 1M bar index after 5M bar j closes
    m5_signal_m1_i: np.ndarray    # 1M bar index at 5M bar j close (for parity stream)


def build_mtf_arrays(swing_5m: int = 5, swing_15m: int = 5) -> MTFArrays:
    m1_df, m5_df, m15_df = load_markets()
    m15_on_m5 = align_htf_to_1m(m5_df, m15_df)

    m1_hi = m1_df["high"].values.astype(float)
    m1_lo = m1_df["low"].values.astype(float)
    m1_cl = m1_df["close"].values.astype(float)
    m1_op = m1_df["open"].values.astype(float)
    m1_atr = m1_df["atr"].values.astype(float)

    m5_hi = m5_df["high"].values.astype(float)
    m5_lo = m5_df["low"].values.astype(float)
    m5_cl = m5_df["close"].values.astype(float)
    m5_op = m5_df["open"].values.astype(float)
    m5_atr = m5_df["atr"].values.astype(float) if "atr" in m5_df.columns else np.full(len(m5_df), np.nan)
    m5_body = np.abs(m5_cl - m5_op)

    _sh1, _sh2 = precompute_last2_swing_highs(m5_hi, swing_5m)
    _sl1, _sl2 = precompute_last2_swing_lows(m5_lo, swing_5m)

    m15_cl = m15_on_m5["close"].values.astype(float)
    m15_op = m15_on_m5["open"].values.astype(float)
    m15_hi = m15_on_m5["high"].values.astype(float)
    m15_lo = m15_on_m5["low"].values.astype(float)
    m15_atr = (
        m15_on_m5["atr"].values.astype(float)
        if "atr" in m15_on_m5.columns
        else np.full(len(m15_on_m5), np.nan)
    )
    m15_idx_on_m5 = htf_bar_index(m5_df.index, m15_df.index)

    # 1M → 5M: last completed 5M bar at each 1M timestamp
    m1_to_m5 = htf_bar_index(m1_df.index, m5_df.index)

    # 5M bar j closes at m5_idx[j+1] start (or end of j's period)
    # First 1M bar strictly after 5M bar j's timestamp = next 1M bar after m5 close
    m5_close_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_signal_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_ts = m5_df.index.values
    m1_ts = m1_df.index.values
    for j in range(len(m5_df)):
        # 5M bar closes at start of next 5M period
        if j + 1 < len(m5_ts):
            close_ts = m5_ts[j + 1]
        else:
            close_ts = m5_ts[j] + np.timedelta64(5, "m")
        pos = int(np.searchsorted(m1_ts, close_ts, side="left"))
        m5_close_m1_i[j] = min(pos, len(m1_df) - 1)
        # Signal at last 1M bar inside 5M bar j
        pos_sig = int(np.searchsorted(m1_ts, m5_ts[j + 1] if j + 1 < len(m5_ts) else close_ts, side="left")) - 1
        m5_signal_m1_i[j] = max(0, min(pos_sig, len(m1_df) - 1))

    return MTFArrays(
        m1_hi=m1_hi,
        m1_lo=m1_lo,
        m1_cl=m1_cl,
        m1_op=m1_op,
        m1_atr=m1_atr,
        m1_n=len(m1_df),
        m1_idx=m1_df.index,
        m5_hi=m5_hi,
        m5_lo=m5_lo,
        m5_cl=m5_cl,
        m5_op=m5_op,
        m5_atr=m5_atr,
        m5_n=len(m5_df),
        m5_idx=m5_df.index,
        m5_sh=precompute_swing_highs(m5_hi, swing_5m),
        m5_sl=precompute_swing_lows(m5_lo, swing_5m),
        m5_sh1=_sh1,
        m5_sh2=_sh2,
        m5_sl1=_sl1,
        m5_sl2=_sl2,
        m5_body=m5_body,
        m15_cl=m15_cl,
        m15_op=m15_op,
        m15_hi=m15_hi,
        m15_lo=m15_lo,
        m15_atr=m15_atr,
        m15_idx_on_m5=m15_idx_on_m5,
        m1_to_m5=m1_to_m5,
        m5_close_m1_i=m5_close_m1_i,
        m5_signal_m1_i=m5_signal_m1_i,
    )
