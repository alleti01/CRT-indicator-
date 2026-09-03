"""Phase53 data loading — 1M, causal 5M, 15M."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m
from phase45.execution.data_1m import load_market_1m

from phase53.config import RESULTS, TIMEZONE


def resample_5m_causal(m1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1M → 5M using standard OHLC (causal completed bars)."""
    o = m1["open"].resample("5min").first()
    h = m1["high"].resample("5min").max()
    l = m1["low"].resample("5min").min()
    c = m1["close"].resample("5min").last()
    m5 = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna(how="any")
    if "atr" in m1.columns:
        m5["atr"] = m1["atr"].resample("5min").last()
    else:
        tr = pd.concat(
            [
                m5["high"] - m5["low"],
                (m5["high"] - m5["close"].shift(1)).abs(),
                (m5["low"] - m5["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        m5["atr"] = tr.rolling(14, min_periods=14).mean()
    return m5


def align_htf_to_1m(m1: pd.DataFrame, htf: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill last completed HTF bar onto 1M index."""
    htf = htf.reindex(htf.index.union(m1.index)).sort_index().ffill()
    return htf.reindex(m1.index, method="ffill")


def htf_bar_index(m1_index: pd.DatetimeIndex, htf_index: pd.DatetimeIndex) -> np.ndarray:
    """Index of last completed HTF bar for each 1M bar."""
    pos = np.searchsorted(htf_index.values, m1_index.values, side="right") - 1
    return np.clip(pos, 0, len(htf_index) - 1)


def load_markets() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    m1 = load_market_1m()
    if "atr" not in m1.columns:
        from phase16.indicators import add_base_indicators
        from phase31.config import frozen_config_15m

        m1 = add_base_indicators(m1, frozen_config_15m())
    m15 = load_replay_market_15m()
    m5 = resample_5m_causal(m1)
    return m1, m5, m15


def document_data(m1: pd.DataFrame, m5: pd.DataFrame, m15: pd.DataFrame) -> dict:
    doc = {
        "timezone": TIMEZONE,
        "session": "RTH 0930-1600 CT for session features only",
        "m1_first": str(m1.index.min()),
        "m1_last": str(m1.index.max()),
        "m1_bars": int(len(m1)),
        "m5_first": str(m5.index.min()),
        "m5_last": str(m5.index.max()),
        "m5_bars": int(len(m5)),
        "m5_resample": "1M OHLC aggregated to 5min closed bars",
        "m15_first": str(m15.index.min()),
        "m15_last": str(m15.index.max()),
        "m15_bars": int(len(m15)),
        "missing_data": "dropna on OHLC; HTF ffill for alignment only",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    return doc
