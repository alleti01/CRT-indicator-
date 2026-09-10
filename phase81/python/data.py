"""Phase81 data loading and long-freeze verification."""
from __future__ import annotations

import pandas as pd

from phase69.python.entry_freeze import config_hash
from phase81.python.config import CANON_PARQUET, long_stream_hash


def load_stream() -> pd.DataFrame:
    df = pd.read_parquet(CANON_PARQUET)
    df = df.loc[df["h1_status"] == "KEEP"].copy()
    df = df.sort_values("entry_ts").reset_index(drop=True)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    return df


def split_sides(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    longs = df[df["direction_m1"] == "LONG"].copy()
    shorts = df[df["direction_m1"] == "SHORT"].copy()
    return longs, shorts


def verify_long_freeze(before: pd.DataFrame, after: pd.DataFrame) -> tuple[bool, str, str]:
    h0 = long_stream_hash(before)
    h1 = long_stream_hash(after)
    return h0 == h1, h0, h1


def combine_portfolio(longs: pd.DataFrame, shorts: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([longs, shorts], ignore_index=True).sort_values("entry_ts").reset_index(drop=True)
