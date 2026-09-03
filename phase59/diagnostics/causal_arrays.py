"""Build MarketArrays / MTFArrays with diagnostic HTF modes."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase53.research.data import align_htf_to_1m, htf_bar_index
from phase58.research.precompute import MarketArrays
from phase58b.research.precompute import MTFArrays
from phase58j.research.lw_data import load_markets_lw
from phase59.diagnostics.htf_causality import HTFMode, build_htf_on_1m, last_completed_label


def build_market_arrays_mode(mode: HTFMode, swing: int = 5) -> MarketArrays:
    m1, m5, m15 = load_markets_lw()
    m5a, m15a, m5_idx, m15_idx = build_htf_on_1m(m1, m5, m15, mode)
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
        sh=precompute_swing_highs(hi, swing), sl=precompute_swing_lows(lo, swing),
        sh1=_sh1, sh2=_sh2, sl1=_sl1, sl2=_sl2,
        m5_cl=m5a["close"].values.astype(float),
        m5_op=m5a["open"].values.astype(float),
        m5_hi=m5a["high"].values.astype(float),
        m5_lo=m5a["low"].values.astype(float),
        m5_atr=m5a["atr"].values.astype(float) if "atr" in m5a.columns else np.full(len(m5a), np.nan),
        m5_idx=m5_idx,
        m15_cl=m15a["close"].values.astype(float),
        m15_op=m15a["open"].values.astype(float),
        m15_hi=m15a["high"].values.astype(float),
        m15_lo=m15a["low"].values.astype(float),
        m15_atr=m15a["atr"].values.astype(float) if "atr" in m15a.columns else np.full(len(m15a), np.nan),
        m15_idx=m15_idx,
        body=body, avg_body=avg_body,
    )


def build_mtf_arrays_mode(mode: HTFMode, swing_5m: int = 5) -> MTFArrays:
    m1_df, m5_df, m15_df = load_markets_lw()
    m5_on_1m, m15_on_1m, m1_to_m5, _m1_to_m15 = build_htf_on_1m(m1_df, m5_df, m15_df, mode)

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

    if mode == "original":
        m15_on_m5 = align_htf_to_1m(m5_df, m15_df)
        m15_idx_on_m5 = htf_bar_index(m5_df.index, m15_df.index)
    elif mode == "causal_a":
        rows = []
        idxs = []
        for ts5 in m5_df.index:
            lab = last_completed_label(ts5, 15)
            pos = int(m15_df.index.searchsorted(lab))
            if pos >= len(m15_df) or m15_df.index[pos] != lab:
                pos = max(0, int(m15_df.index.searchsorted(lab, side="right") - 1))
            rows.append(m15_df.iloc[pos])
            idxs.append(pos)
        m15_on_m5 = pd.DataFrame(rows, index=m5_df.index)
        m15_idx_on_m5 = np.array(idxs, dtype=int)
    else:
        m15_on_m5 = align_htf_to_1m(m5_df, m15_df)
        m15_idx_on_m5 = htf_bar_index(m5_df.index, m15_df.index)

    m15_cl = m15_on_m5["close"].values.astype(float)
    m15_op = m15_on_m5["open"].values.astype(float)
    m15_hi = m15_on_m5["high"].values.astype(float)
    m15_lo = m15_on_m5["low"].values.astype(float)
    m15_atr = (
        m15_on_m5["atr"].values.astype(float)
        if "atr" in m15_on_m5.columns
        else np.full(len(m5_df), np.nan)
    )

    m5_close_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_signal_m1_i = np.zeros(len(m5_df), dtype=int)
    m5_ts = m5_df.index.values
    m1_ts = m1_df.index.values
    for j in range(len(m5_df)):
        if j + 1 < len(m5_ts):
            close_ts = m5_ts[j + 1]
        else:
            close_ts = m5_ts[j] + np.timedelta64(5, "m")
        pos = int(np.searchsorted(m1_ts, close_ts, side="left"))
        m5_close_m1_i[j] = min(pos, len(m1_df) - 1)
        pos_sig = int(np.searchsorted(m1_ts, m5_ts[j + 1] if j + 1 < len(m5_ts) else close_ts, side="left")) - 1
        m5_signal_m1_i[j] = max(0, min(pos_sig, len(m1_df) - 1))

    mtf = MTFArrays(
        m1_hi=m1_hi, m1_lo=m1_lo, m1_cl=m1_cl, m1_op=m1_op, m1_atr=m1_atr,
        m1_n=len(m1_df), m1_idx=m1_df.index,
        m5_hi=m5_hi, m5_lo=m5_lo, m5_cl=m5_cl, m5_op=m5_op, m5_atr=m5_atr,
        m5_n=len(m5_df), m5_idx=m5_df.index,
        m5_sh=precompute_swing_highs(m5_hi, swing_5m),
        m5_sl=precompute_swing_lows(m5_lo, swing_5m),
        m5_sh1=_sh1, m5_sh2=_sh2, m5_sl1=_sl1, m5_sl2=_sl2, m5_body=m5_body,
        m15_cl=m15_cl, m15_op=m15_op, m15_hi=m15_hi, m15_lo=m15_lo, m15_atr=m15_atr,
        m15_idx_on_m5=m15_idx_on_m5, m1_to_m5=m1_to_m5,
        m5_close_m1_i=m5_close_m1_i, m5_signal_m1_i=m5_signal_m1_i,
    )
    mtf._m5_on_1m = m5_on_1m  # type: ignore[attr-defined]
    mtf._m15_on_1m = m15_on_1m  # type: ignore[attr-defined]
    mtf._htf_mode = mode  # type: ignore[attr-defined]
    return mtf
