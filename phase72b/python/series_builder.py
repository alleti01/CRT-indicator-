"""Build Pine-equivalent per-bar series from local 1M/5M/15M data."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase52.research.swings import precompute_swing_highs, precompute_swing_lows
from phase60.python.developing_htf import build_developing_htf_vectorized
from phase72b.python.config import PineConfig, DEFAULT_CFG
from phase72b.python.pine_atr import atr_use, sma_range_atr


@dataclass
class PineSeries:
    """Per-1M-bar arrays mirroring Pine unconditional series."""

    idx: pd.DatetimeIndex
    op: np.ndarray
    hi: np.ndarray
    lo: np.ndarray
    cl: np.ndarray
    atr_use: np.ndarray
    m5_o: np.ndarray
    m5_h: np.ndarray
    m5_l: np.ndarray
    m5_c: np.ndarray
    m5_prev_c: np.ndarray
    m5_prev_h: np.ndarray
    m5_prev_l: np.ndarray
    m5_atr: np.ndarray
    m15_o: np.ndarray
    m15_h: np.ndarray
    m15_l: np.ndarray
    m15_c: np.ndarray
    m15_prev_c: np.ndarray
    m15_atr: np.ndarray
    m15_h4: np.ndarray
    m15_l4: np.ndarray
    m15_c12: np.ndarray
    m5_last_sh: np.ndarray
    m5_prev_sh: np.ndarray
    m5_last_sl: np.ndarray
    m5_prev_sl: np.ndarray
    sh_at_i: np.ndarray
    sh_at_i10: np.ndarray
    sl_at_i: np.ndarray
    sl_at_i10: np.ndarray
    rh1m20: np.ndarray
    rl1m20: np.ndarray
    rh5m20: np.ndarray
    rl5m20: np.ndarray
    rh1m12: np.ndarray
    rl1m12: np.ndarray
    rh15m8: np.ndarray
    rl15m8: np.ndarray
    ll12_1m: np.ndarray
    hh12_1m: np.ndarray
    ll_pb_1m: np.ndarray
    hh_pb_1m: np.ndarray
    m5_range_sma4: np.ndarray
    imp1m20: np.ndarray
    imp5m20: np.ndarray
    imp15m8: np.ndarray
    m5_completed_j: np.ndarray
    m15_completed_j: np.ndarray


def _pivot_series(hi: np.ndarray, lo: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray]:
    n = len(hi)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(period, n - period):
        wh = hi[i - period : i + period + 1]
        wl = lo[i - period : i + period + 1]
        if hi[i] == np.max(wh):
            ph[i] = hi[i]
        if lo[i] == np.min(wl):
            pl[i] = lo[i]
    return ph, pl


def _valuewhen_last_two(pivot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pine ta.valuewhen occurrence 0 and 1 forward-filled."""
    n = len(pivot)
    cur = np.full(n, np.nan)
    prev = np.full(n, np.nan)
    last = np.nan
    prior = np.nan
    for i in range(n):
        if np.isfinite(pivot[i]):
            prior = last
            last = pivot[i]
        cur[i] = last
        prev[i] = prior
    return cur, prev


def _ffill_pivot_state_on_1m(
    m1_idx: pd.DatetimeIndex,
    native_idx: pd.DatetimeIndex,
    native_pivot: np.ndarray,
    completed_j: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Track last two pivot values from completed HTF bars (Pine var m5LastSH)."""
    n = len(m1_idx)
    pos = {t: j for j, t in enumerate(native_idx)}
    native_last = np.full(len(native_idx), np.nan)
    native_prev = np.full(len(native_idx), np.nan)
    last = np.nan
    prior = np.nan
    for j in range(len(native_idx)):
        if np.isfinite(native_pivot[j]):
            prior = last
            last = native_pivot[j]
        native_last[j] = last
        native_prev[j] = prior

    out_last = np.full(n, np.nan)
    out_prev = np.full(n, np.nan)
    for i in range(n):
        cj = int(completed_j[i])
        if cj >= 0:
            out_last[i] = native_last[cj]
            out_prev[i] = native_prev[cj]
        elif i > 0:
            out_last[i] = out_last[i - 1]
            out_prev[i] = out_prev[i - 1]
    return out_last, out_prev


def _prev_bucket_close(m1: pd.DataFrame, minutes: int) -> np.ndarray:
    g = m1.index.floor(f"{minutes}min")
    bucket_close = m1.groupby(g)["close"].last()
    prev_map = {}
    buckets = sorted(bucket_close.index)
    for k in range(1, len(buckets)):
        prev_map[buckets[k]] = float(bucket_close.iloc[k - 1])
    out = np.full(len(m1), np.nan)
    for i, ts in enumerate(m1.index):
        b = ts.floor(f"{minutes}min")
        out[i] = prev_map.get(b, np.nan)
    return out


def _prev_bucket_extreme(m1: pd.DataFrame, minutes: int, col: str) -> np.ndarray:
    g = m1.index.floor(f"{minutes}min")
    if col == "high":
        bucket_val = m1.groupby(g)["high"].max()
    else:
        bucket_val = m1.groupby(g)["low"].min()
    prev_map = {}
    buckets = sorted(bucket_val.index)
    for k in range(1, len(buckets)):
        prev_map[buckets[k]] = float(bucket_val.iloc[k - 1])
    out = np.full(len(m1), np.nan)
    for i, ts in enumerate(m1.index):
        b = ts.floor(f"{minutes}min")
        out[i] = prev_map.get(b, np.nan)
    return out


def _align_completed_ref(
    m1_idx: pd.DatetimeIndex,
    native_idx: pd.DatetimeIndex,
    native_series: np.ndarray,
    completed_j: np.ndarray,
    lag: int,
) -> np.ndarray:
    n = len(m1_idx)
    out = np.full(n, np.nan)
    for i in range(n):
        cj = int(completed_j[i])
        j = cj - lag
        if j >= 0:
            out[i] = native_series[j]
    return out


def build_pine_series(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    cfg: PineConfig = DEFAULT_CFG,
) -> PineSeries:
    dev = build_developing_htf_vectorized(m1, m5.index, m15.index)
    op = m1["open"].values.astype(float)
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr_raw = sma_range_atr(hi, lo, cfg.atr_period)
    atr_u = atr_use(atr_raw)

    m5_o = dev.m5_dev_op
    m5_h = dev.m5_dev_hi
    m5_l = dev.m5_dev_lo
    m5_c = dev.m5_dev_cl
    m15_o = dev.m15_dev_op
    m15_h = dev.m15_dev_hi
    m15_l = dev.m15_dev_lo
    m15_c = dev.m15_dev_cl

    m5_prev_c = _prev_bucket_close(m1, 5)
    m5_prev_h = _prev_bucket_extreme(m1, 5, "high")
    m5_prev_l = _prev_bucket_extreme(m1, 5, "low")
    m15_prev_c = _prev_bucket_close(m1, 15)

    m5_atr = atr_use(sma_range_atr(m5_h, m5_l, cfg.atr_period))
    m15_atr = atr_use(sma_range_atr(m15_h, m15_l, cfg.atr_period))

    m5_hi_n = m5["high"].values.astype(float)
    m5_lo_n = m5["low"].values.astype(float)
    m5_ph, m5_pl = _pivot_series(m5_hi_n, m5_lo_n, cfg.swing_period)
    m5_last_sh, m5_prev_sh = _ffill_pivot_state_on_1m(
        m1.index, m5.index, m5_ph, dev.m5_completed_j
    )
    m5_last_sl, m5_prev_sl = _ffill_pivot_state_on_1m(
        m1.index, m5.index, m5_pl, dev.m5_completed_j
    )

    m15_hi_n = m15["high"].values.astype(float)
    m15_lo_n = m15["low"].values.astype(float)
    m15_cl_n = m15["close"].values.astype(float)
    m15_h4 = _align_completed_ref(m1.index, m15.index, m15_hi_n, dev.m15_completed_j, 4)
    m15_l4 = _align_completed_ref(m1.index, m15.index, m15_lo_n, dev.m15_completed_j, 4)
    m15_c12 = _align_completed_ref(m1.index, m15.index, m15_cl_n, dev.m15_completed_j, 12)

    ph1, pl1 = _pivot_series(hi, lo, cfg.swing_period)
    sh_cur, sh_prev = _valuewhen_last_two(ph1)
    sl_cur, sl_prev = _valuewhen_last_two(pl1)
    last_sh, _ = _valuewhen_last_two(ph1)
    last_sl, _ = _valuewhen_last_two(pl1)

    sh_at_i = np.where(np.isfinite(sh_cur), sh_cur, last_sh)
    sl_at_i = np.where(np.isfinite(sl_cur), sl_cur, last_sl)
    sh_at_i10 = np.where(np.isfinite(sh_prev), sh_prev, np.roll(last_sh, 10))
    sl_at_i10 = np.where(np.isfinite(sl_prev), sl_prev, np.roll(last_sl, 10))
    sh_at_i10[:10] = np.where(np.isfinite(sh_prev[:10]), sh_prev[:10], last_sh[:10])
    sl_at_i10[:10] = np.where(np.isfinite(sl_prev[:10]), sl_prev[:10], last_sl[:10])

    lb20 = 20
    imp_lb = 12
    rh1m20 = pd.Series(hi).rolling(lb20, min_periods=1).max().values
    rl1m20 = pd.Series(lo).rolling(lb20, min_periods=1).min().values
    rh5m20 = pd.Series(m5_h).rolling(lb20, min_periods=1).max().values
    rl5m20 = pd.Series(m5_l).rolling(lb20, min_periods=1).min().values
    rh1m12 = pd.Series(hi).rolling(imp_lb, min_periods=1).max().values
    rl1m12 = pd.Series(lo).rolling(imp_lb, min_periods=1).min().values
    rh15m8 = pd.Series(m15_h).rolling(8, min_periods=1).max().values
    rl15m8 = pd.Series(m15_l).rolling(8, min_periods=1).min().values
    ll12_1m = rl1m12
    hh12_1m = rh1m12
    ll_pb_1m = pd.Series(lo).rolling(cfg.progress_lb_1m, min_periods=1).min().values
    hh_pb_1m = pd.Series(hi).rolling(cfg.progress_lb_1m, min_periods=1).max().values
    m5_range_sma4 = pd.Series(m5_h - m5_l).rolling(4, min_periods=1).mean().values

    return PineSeries(
        idx=m1.index,
        op=op,
        hi=hi,
        lo=lo,
        cl=cl,
        atr_use=atr_u,
        m5_o=m5_o,
        m5_h=m5_h,
        m5_l=m5_l,
        m5_c=m5_c,
        m5_prev_c=m5_prev_c,
        m5_prev_h=m5_prev_h,
        m5_prev_l=m5_prev_l,
        m5_atr=m5_atr,
        m15_o=m15_o,
        m15_h=m15_h,
        m15_l=m15_l,
        m15_c=m15_c,
        m15_prev_c=m15_prev_c,
        m15_atr=m15_atr,
        m15_h4=m15_h4,
        m15_l4=m15_l4,
        m15_c12=m15_c12,
        m5_last_sh=m5_last_sh,
        m5_prev_sh=m5_prev_sh,
        m5_last_sl=m5_last_sl,
        m5_prev_sl=m5_prev_sl,
        sh_at_i=sh_at_i,
        sh_at_i10=sh_at_i10,
        sl_at_i=sl_at_i,
        sl_at_i10=sl_at_i10,
        rh1m20=rh1m20,
        rl1m20=rl1m20,
        rh5m20=rh5m20,
        rl5m20=rl5m20,
        rh1m12=rh1m12,
        rl1m12=rl1m12,
        rh15m8=rh15m8,
        rl15m8=rl15m8,
        ll12_1m=ll12_1m,
        hh12_1m=hh12_1m,
        ll_pb_1m=ll_pb_1m,
        hh_pb_1m=hh_pb_1m,
        m5_range_sma4=m5_range_sma4,
        imp1m20=rh1m20 - rl1m20,
        imp5m20=rh5m20 - rl5m20,
        imp15m8=rh15m8 - rl15m8,
        m5_completed_j=dev.m5_completed_j,
        m15_completed_j=dev.m15_completed_j,
    )
