"""Load existing NQ 1-minute history. No new paid data."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.data_loader import load_ohlcv_csv
from phase45.execution.config import RAW_1M_PATHS
from phase58j.research.lw_data import EXTENSION, BRIDGE, lw_1m_paths
from phase83.python.config import ATR_PERIOD, EXCHANGE_TZ, NY_TZ


def load_nq_1m() -> tuple[pd.DataFrame, dict]:
    paths = [p for p in lw_1m_paths() if p.exists() and p.stat().st_size > 200]
    parts = [load_ohlcv_csv(str(p), source_timezone="UTC") for p in paths]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if df.index.tz is None:
        df.index = df.index.tz_localize(EXCHANGE_TZ)
    else:
        df.index = df.index.tz_convert(EXCHANGE_TZ)

    tr = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs(),
        ),
    )
    df["atr"] = tr.rolling(ATR_PERIOD, min_periods=ATR_PERIOD).mean()
    df["volume"] = df["volume"].astype(float)

    ny = df.index.tz_convert(NY_TZ)
    meta = {
        "dataset": "lw_1m_paths (phase16/18 raw + postwindow bridge + phase58j extension)",
        "instrument": "NQ continuous 1m",
        "contract_construction": "vendor continuous / Databento-style roll concatenated; last duplicate kept",
        "source_paths": [str(p) for p in paths],
        "bridge_present": BRIDGE.exists(),
        "extension_present": EXTENSION.exists(),
        "raw_1m_core": [str(p) for p in RAW_1M_PATHS if p.exists()],
        "timezone_stored": EXCHANGE_TZ,
        "timezone_sessions": NY_TZ,
        "index_min": str(df.index.min()),
        "index_max": str(df.index.max()),
        "n_bars": int(len(df)),
        "ohlc_bad": int((df["high"] < df["low"]).sum()),
        "atr_period": ATR_PERIOD,
        "ny_min": str(ny.min()),
        "ny_max": str(ny.max()),
    }
    return df, meta


def arrays(df: pd.DataFrame) -> dict:
    ny = df.index.tz_convert(NY_TZ)
    return {
        "ts": df.index,
        "ny": ny,
        "op": df["open"].to_numpy(dtype=float),
        "hi": df["high"].to_numpy(dtype=float),
        "lo": df["low"].to_numpy(dtype=float),
        "cl": df["close"].to_numpy(dtype=float),
        "vol": df["volume"].to_numpy(dtype=float),
        "atr": df["atr"].to_numpy(dtype=float),
        "n": len(df),
    }
