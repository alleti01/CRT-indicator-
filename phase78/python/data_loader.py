"""Phase78 data loading — OHLCV only, no trading logic."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase16.data_loader import load_ohlcv_csv

from .config import ATR_PERIOD, CONTINUOUS_METHOD, RAW_1M_PATHS, SYMBOL, TIMEZONE, TIMEZONE_UTC


def load_nq_1m(*, paths: tuple[Path, ...] | None = None) -> pd.DataFrame:
    paths = paths or RAW_1M_PATHS
    parts: list[pd.DataFrame] = []
    loaded: list[str] = []
    for p in paths:
        if not p.exists() or p.stat().st_size < 200:
            continue
        parts.append(load_ohlcv_csv(str(p), source_timezone=TIMEZONE_UTC))
        loaded.append(str(p))
    if not parts:
        raise FileNotFoundError("No Phase78 1m data files found")
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.attrs["loaded_paths"] = loaded
    return df


def add_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.DataFrame:
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


def attach_et(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    idx = df.index.tz_localize(TIMEZONE_UTC) if df.index.tz is None else df.index
    out["ts_et"] = idx.tz_convert(TIMEZONE)
    return out


def data_audit(df: pd.DataFrame) -> dict:
    dup = int(df.index.duplicated().sum())
    bad_ohlc = int(((df["high"] < df["low"]) | (df["high"] < df["open"]) | (df["high"] < df["close"])).sum())
    return {
        "symbol": SYMBOL,
        "continuous_method": CONTINUOUS_METHOD,
        "bars": len(df),
        "start_utc": str(df.index.min()),
        "end_utc": str(df.index.max()),
        "timezone_storage": str(df.index.tz),
        "timezone_research": TIMEZONE,
        "duplicate_bars": dup,
        "bad_ohlc": bad_ohlc,
        "loaded_paths": df.attrs.get("loaded_paths", []),
    }
