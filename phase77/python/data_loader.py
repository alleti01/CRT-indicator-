"""Phase77 — Jan 2024 pilot data (LEVEL 1 trades + LEVEL 0 1m OHLCV)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase68.python.trades_loader import load_trades

from .config import M1_PILOT, PILOT_END, PILOT_START, TIMEZONE, TRADES_PILOT


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    out = df.copy()
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - out["close"].shift(1)).abs(),
            (out["low"] - out["close"].shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr"] = tr.rolling(period, min_periods=period).mean()
    return out


def load_jan2024_m1() -> pd.DataFrame:
    df = load_ohlcv_csv(str(M1_PILOT), source_timezone="UTC")
    start = pd.Timestamp(PILOT_START, tz="UTC")
    end = pd.Timestamp(PILOT_END, tz="UTC")
    df = df[(df.index >= start) & (df.index < end)].copy()
    df = add_atr(df)
    df["ts_et"] = df.index.tz_convert(TIMEZONE)
    return df.sort_index()


def load_jan2024_trades() -> pd.DataFrame:
    return load_trades(TRADES_PILOT)


def data_inventory(m1: pd.DataFrame, trades: pd.DataFrame) -> dict:
    classified = int((trades["is_buy"] | trades["is_sell"]).sum())
    return {
        "pilot_range": f"{trades['ts_local'].min()} → {trades['ts_local'].max()}",
        "n_trades": len(trades),
        "n_trades_classified": classified,
        "aggressor_method": "Databento side B=buy aggressor, A=sell aggressor",
        "n_1m_bars": len(m1),
        "m1_range": f"{m1.index.min()} → {m1.index.max()}",
        "trade_timestamp_resolution": "microsecond (event timestamp)",
        "quote_bbo": False,
        "depth_mbp": False,
        "level_0": True,
        "level_1": True,
        "level_2": False,
        "level_3": False,
        "profile_type": "TRUE_TRADE_VAP_PROFILE",
        "absorption_type": "TRADE_RESPONSE_ABSORPTION_PROXY",
        "vap_from_trades": True,
    }
