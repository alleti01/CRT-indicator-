"""Phase67 — data integrity + causal rolling structure."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase58j.research.lw_data import load_market_1m_lw


@dataclass
class MarketPre:
    hi: np.ndarray
    lo: np.ndarray
    op: np.ndarray
    cl: np.ndarray
    atr: np.ndarray
    n: int
    idx: pd.DatetimeIndex
    # prior-only rolling extremes (exclude current bar)
    hi_3: np.ndarray
    lo_3: np.ndarray
    hi_5: np.ndarray
    lo_5: np.ndarray
    hi_10: np.ndarray
    lo_10: np.ndarray
    hi_20: np.ndarray
    lo_20: np.ndarray
    range_5: np.ndarray
    range_10: np.ndarray
    range_20: np.ndarray
    mid_10: np.ndarray
    body: np.ndarray
    bar_range: np.ndarray


def _prior_roll(arr: np.ndarray, w: int, fn) -> np.ndarray:
    out = np.full(len(arr), np.nan)
    for i in range(w, len(arr)):
        out[i] = fn(arr[i - w : i])
    return out


def check_data_integrity(df: pd.DataFrame) -> dict:
    dup = int(df.index.duplicated().sum())
    ohlc_bad = int(
        ((df["high"] < df[["open", "close"]].max(axis=1)) |
         (df["low"] > df[["open", "close"]].min(axis=1))).sum()
    )
    atr_bad = int(df["atr"].isna().sum()) if "atr" in df else len(df)
    gaps = df.index.to_series().diff()
    gap_2m = int((gaps > pd.Timedelta(minutes=2)).sum())
    return {
        "start": str(df.index.min()),
        "end": str(df.index.max()),
        "bars": len(df),
        "duplicate_bars": dup,
        "ohlc_invalid": ohlc_bad,
        "atr_nan": atr_bad,
        "gaps_gt_2m": gap_2m,
        "monotonic": bool(df.index.is_monotonic_increasing),
        "pass": dup == 0 and ohlc_bad == 0 and df.index.is_monotonic_increasing,
    }


def build_precomputed(warmup: int = 25) -> tuple[MarketPre, dict]:
    df = load_market_1m_lw()
    integrity = check_data_integrity(df)
    hi = df["high"].values.astype(float)
    lo = df["low"].values.astype(float)
    op = df["open"].values.astype(float)
    cl = df["close"].values.astype(float)
    atr = df["atr"].values.astype(float)
    atr = np.where(np.isfinite(atr) & (atr > 0), atr, np.nanmedian(atr))

    pre = MarketPre(
        hi=hi, lo=lo, op=op, cl=cl, atr=atr, n=len(df), idx=df.index,
        hi_3=_prior_roll(hi, 3, np.max),
        lo_3=_prior_roll(lo, 3, np.min),
        hi_5=_prior_roll(hi, 5, np.max),
        lo_5=_prior_roll(lo, 5, np.min),
        hi_10=_prior_roll(hi, 10, np.max),
        lo_10=_prior_roll(lo, 10, np.min),
        hi_20=_prior_roll(hi, 20, np.max),
        lo_20=_prior_roll(lo, 20, np.min),
        range_5=_prior_roll(hi, 5, np.max) - _prior_roll(lo, 5, np.min),
        range_10=_prior_roll(hi, 10, np.max) - _prior_roll(lo, 10, np.min),
        range_20=_prior_roll(hi, 20, np.max) - _prior_roll(lo, 20, np.min),
        mid_10=(_prior_roll(hi, 10, np.max) + _prior_roll(lo, 10, np.min)) / 2,
        body=np.abs(cl - op),
        bar_range=hi - lo,
    )
    return pre, integrity
