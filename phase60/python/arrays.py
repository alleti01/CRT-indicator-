"""Phase60 MTFArrays / MarketArrays with causal developing HTF."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase58.research.precompute import MarketArrays
from phase58b.research.precompute import MTFArrays
from phase58j.research.lw_data import load_markets_lw
from phase59.diagnostics.htf_causality import _labels_last_completed, _pos_for_labels
from phase60.python.developing_htf import DevelopingHTFArrays, build_developing_htf_vectorized


def build_market_arrays_phase60(swing: int = 5) -> MarketArrays:
    """MarketArrays with developing 5M/15M OHLC aligned per 1M bar."""
    m1, m5, m15 = load_markets_lw()
    dev = build_developing_htf_vectorized(m1, m5.index, m15.index)

    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    body = np.abs(cl - op)
    avg_body = pd.Series(body).rolling(20, min_periods=1).mean().values
    _sh1, _sh2 = precompute_last2_swing_highs(hi, swing)
    _sl1, _sl2 = precompute_last2_swing_lows(lo, swing)

    m5_atr = m5["atr"].values.astype(float) if "atr" in m5.columns else np.full(len(m5), np.nan)
    m15_atr = m15["atr"].values.astype(float) if "atr" in m15.columns else np.full(len(m15), np.nan)
    m5_atr_1m = np.where(dev.m5_completed_j >= 0, m5_atr[np.clip(dev.m5_completed_j, 0, len(m5) - 1)], np.nan)
    m15_atr_1m = np.where(
        dev.m15_completed_j >= 0, m15_atr[np.clip(dev.m15_completed_j, 0, len(m15) - 1)], np.nan
    )

    return MarketArrays(
        hi=hi,
        lo=lo,
        cl=cl,
        op=op,
        atr=atr,
        n=len(m1),
        idx=m1.index,
        sh=precompute_swing_highs(hi, swing),
        sl=precompute_swing_lows(lo, swing),
        sh1=_sh1,
        sh2=_sh2,
        sl1=_sl1,
        sl2=_sl2,
        m5_cl=dev.m5_dev_cl,
        m5_op=dev.m5_dev_op,
        m5_hi=dev.m5_dev_hi,
        m5_lo=dev.m5_dev_lo,
        m5_atr=m5_atr_1m,
        m5_idx=dev.m5_bucket_j,
        m15_cl=dev.m15_dev_cl,
        m15_op=dev.m15_dev_op,
        m15_hi=dev.m15_dev_hi,
        m15_lo=dev.m15_dev_lo,
        m15_atr=m15_atr_1m,
        m15_idx=dev.m15_bucket_j,
        body=body,
        avg_body=avg_body,
    )


def build_mtf_arrays_phase60(swing_5m: int = 5) -> MTFArrays:
    """MTFArrays: completed native 5M/15M for swings; developing state on m.phase60."""
    m1_df, m5_df, m15_df = load_markets_lw()
    dev = build_developing_htf_vectorized(m1_df, m5_df.index, m15_df.index)

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

    # 15M completed-only series aligned to 5M (causal A semantics for history)
    lab15_lc = _labels_last_completed(m5_df.index, 15)
    m15_lc = m15_df.reindex(lab15_lc)
    m15_cl = m15_lc["close"].values.astype(float)
    m15_op = m15_lc["open"].values.astype(float)
    m15_hi = m15_lc["high"].values.astype(float)
    m15_lo = m15_lc["low"].values.astype(float)
    m15_atr = (
        m15_lc["atr"].values.astype(float)
        if "atr" in m15_lc.columns
        else np.full(len(m5_df), np.nan)
    )
    m15_idx_on_m5 = _pos_for_labels(m15_df.index, lab15_lc)

    # m1_to_m5: completed 5M index (swings / history); developing bucket in phase60.dev
    lab5_lc = _labels_last_completed(m1_df.index, 5)
    m1_to_m5 = _pos_for_labels(m5_df.index, lab5_lc)

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
    mtf.phase60 = dev  # type: ignore[attr-defined]
    return mtf
