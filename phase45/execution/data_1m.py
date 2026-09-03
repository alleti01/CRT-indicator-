"""Load stitched 1m NQ market data."""

from __future__ import annotations

import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import pine_sma
from phase29.config import NQ_DOLLARS_PER_POINT, ROUND_TURN_COST_USD

from .config import RAW_1M_PATHS


def load_market_1m() -> pd.DataFrame:
    parts = [load_ohlcv_csv(str(p), source_timezone="UTC") for p in RAW_1M_PATHS if p.exists()]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    atr = (df["high"] - df["low"]).rolling(14).mean()
    df["atr"] = atr
    vol_sma = pine_sma(df["volume"].astype(float), 20)
    df["rel_volume"] = df["volume"].astype(float) / vol_sma.replace(0, pd.NA)
    df["vol_ma5"] = df["volume"].astype(float).rolling(5).mean()
    return df


def cost_r(entry: float, stop: float, multiplier: float = 1.0) -> float:
    risk = abs(entry - stop)
    if risk <= 0:
        return 0.0
    return (ROUND_TURN_COST_USD * multiplier) / (risk * NQ_DOLLARS_PER_POINT)
