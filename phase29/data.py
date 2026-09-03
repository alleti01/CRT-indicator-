"""Load 15m market and frozen CRT V2 signals."""

from __future__ import annotations

import pandas as pd

from phase16.config import FrozenConfig
from phase16.crt_setup_v2 import (
    SetupV2Archetype,
    SetupV2Qualification,
    SetupV2Variant,
    run_setup_v2_backtest,
)
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators

from phase28.resample_timeframes import aggregate_from_5m

from .config import COMMON_END, COMMON_START, NQ_5M_PATHS, VARIANT_ID, frozen_config_15m


def load_market_15m() -> pd.DataFrame:
    config = frozen_config_15m()
    frames = [load_ohlcv_csv(p, exchange_timezone=config.exchange_timezone) for p in NQ_5M_PATHS]
    base5 = pd.concat(frames).sort_index()
    base5 = base5[~base5.index.duplicated(keep="last")]
    market = aggregate_from_5m(base5, 15)
    return add_base_indicators(market, config)


def extract_signals(
    market: pd.DataFrame,
    *,
    start: str = COMMON_START,
    end: str = COMMON_END,
) -> pd.DataFrame:
    variant = SetupV2Variant(
        SetupV2Archetype.NEXT_BAR,
        SetupV2Qualification.LEGACY_QUALIFIED,
        6,
    )
    trades, *_ = run_setup_v2_backtest(
        market,
        variant=variant,
        start=start,
        end=end,
        config=frozen_config_15m(),
    )
    if trades.empty:
        return trades
    signals = trades.copy().reset_index(drop=True)
    signals["signal_id"] = signals.index
    signals["variant_id"] = VARIANT_ID
    for col in ("entry_timestamp", "confirm_timestamp", "bos_timestamp", "setup_timestamp", "exit_timestamp"):
        if col in signals.columns:
            signals[col] = pd.to_datetime(signals[col], utc=True).dt.tz_convert(
                FrozenConfig().exchange_timezone
            )
    return signals
