"""Load extended NQ 15m market data for Phase 36 replay."""

from __future__ import annotations

import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators
from phase28.resample_timeframes import aggregate_from_5m
from phase31.config import frozen_config_15m

from .config import NQ_5M_PATHS, REPLAY_END, REPLAY_START


def load_replay_market_15m() -> pd.DataFrame:
    """Construct causal 15m bars from earliest local 5m data through REPLAY_END."""
    parts = [load_ohlcv_csv(p) for p in NQ_5M_PATHS]
    base = pd.concat(parts).sort_index()
    base = base[~base.index.duplicated(keep="last")]
    base = base.loc[REPLAY_START:REPLAY_END]
    market = aggregate_from_5m(base, 15)
    return add_base_indicators(market, frozen_config_15m())
