"""Load causal NQ 1m OHLCV stack for Phase76."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from phase16.data_loader import load_ohlcv_csv

from .config import RAW_1M_PATHS, TIMEZONE


def load_nq_1m(*, paths: tuple[Path, ...] | None = None) -> pd.DataFrame:
    """Stitch configured 1m CSVs, dedupe, sort — UTC index."""
    paths = paths or RAW_1M_PATHS
    parts: list[pd.DataFrame] = []
    loaded: list[str] = []
    for p in paths:
        if not p.exists() or p.stat().st_size < 200:
            continue
        parts.append(load_ohlcv_csv(str(p), source_timezone="UTC"))
        loaded.append(str(p))
    if not parts:
        raise FileNotFoundError("No Phase76 1m data files found")
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.sort_index()
    df.attrs["loaded_paths"] = loaded
    return df


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


def to_et(df: pd.DataFrame) -> pd.DataFrame:
    """Attach America/New_York localized index as `ts_et`."""
    out = df.copy()
    if df.index.tz is None:
        idx = df.index.tz_localize("UTC")
    else:
        idx = df.index
    out["ts_et"] = idx.tz_convert(TIMEZONE)
    return out


def data_inventory(df: pd.DataFrame) -> dict:
    """Summary for PHASE76_DATA_AUDIT."""
    return {
        "symbol": "NQ.v.0",
        "bars": len(df),
        "start_utc": str(df.index.min()),
        "end_utc": str(df.index.max()),
        "columns": list(df.columns),
        "loaded_paths": df.attrs.get("loaded_paths", []),
        "timezone_storage": str(df.index.tz),
        "timezone_research": TIMEZONE,
    }
