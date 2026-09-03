"""Load causal 15m NQ market data."""

from __future__ import annotations

import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators
from phase28.resample_timeframes import aggregate_from_5m

from .config import COMMON_END, COMMON_START, NQ_5M_PATHS, frozen_config_15m


def load_base_5m() -> pd.DataFrame:
    parts = [load_ohlcv_csv(p) for p in NQ_5M_PATHS]
    base = pd.concat(parts).sort_index()
    base = base[~base.index.duplicated(keep="last")]
    return base.loc[COMMON_START:COMMON_END]


def load_market_15m() -> pd.DataFrame:
    base5 = load_base_5m()
    market = aggregate_from_5m(base5, 15)
    return add_base_indicators(market, frozen_config_15m())
