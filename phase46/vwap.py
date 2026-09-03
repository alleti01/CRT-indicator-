"""Causal session VWAP and related 1m features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.resample import cme_session_date

from .config import VWAP_PRICE_SOURCE, VWAP_TIMEZONE


def hlc3(frame: pd.DataFrame) -> pd.Series:
    return (frame["high"].astype(float) + frame["low"].astype(float) + frame["close"].astype(float)) / 3.0


def attach_session_vwap(market: pd.DataFrame) -> pd.DataFrame:
    """Compute causal CME-session VWAP on 1m bars.

    Session boundary: CME trading date via ``cme_session_date`` (18:00 CT rollover).
    Formula: cumulative(HLC3 * volume) / cumulative(volume) within each session.
    Overnight ETH bars included; VWAP accumulates from session open at 18:00 CT.
    """
    df = market.copy()
    if df.index.tz is None:
        raise TypeError("market index must be timezone-aware")
    px = hlc3(df) if VWAP_PRICE_SOURCE == "HLC3" else df["close"].astype(float)
    df["hlc3"] = px
    df["session_date"] = cme_session_date(df.index)
    df["pv"] = px * df["volume"].astype(float)
    g = df.groupby("session_date", sort=False)
    df["vwap"] = g["pv"].cumsum() / g["volume"].cumsum().replace(0, np.nan)
    df["vwap_slope_1"] = df["vwap"].diff(1)
    for n in (3, 5, 10):
        df[f"vwap_slope_{n}"] = (df["vwap"] - df["vwap"].shift(n)) / n
    return df


def vwap_at_index(market: pd.DataFrame, i: int) -> float:
    if i < 0 or i >= len(market):
        return np.nan
    return float(market.iloc[i]["vwap"])


def signed_vwap_distance(entry: float, vwap: float, direction: str) -> float:
    """Positive = favorable (long above, short below)."""
    d = 1 if str(direction).lower() == "long" else -1
    return d * (entry - vwap)


def atr_distance(entry: float, vwap: float, atr: float) -> float:
    if not np.isfinite(atr) or atr <= 0:
        return np.nan
    return abs(entry - vwap) / atr


def detect_reclaim(
    market: pd.DataFrame,
    start_i: int,
    end_i: int,
    direction: str,
) -> bool:
    """V2: causal reclaim/loss during [start_i, end_i] inclusive."""
    d = 1 if str(direction).lower() == "long" else -1
    touched = False
    for i in range(max(0, start_i), min(len(market), end_i + 1)):
        row = market.iloc[i]
        vwap = float(row["vwap"])
        if not np.isfinite(vwap):
            continue
        hi, lo, cl = float(row.high), float(row.low), float(row.close)
        if d == 1:
            if lo <= vwap:
                touched = True
            if touched and cl > vwap and i == end_i:
                return True
        else:
            if hi >= vwap:
                touched = True
            if touched and cl < vwap and i == end_i:
                return True
    return False


def detect_reclaim_window(
    market: pd.DataFrame,
    start_i: int,
    end_i: int,
    direction: str,
) -> bool:
    """V2: reclaim must complete by end_i (B1 confirmation bar)."""
    d = 1 if str(direction).lower() == "long" else -1
    touched = False
    for i in range(max(0, start_i), min(len(market), end_i + 1)):
        row = market.iloc[i]
        vwap = float(row["vwap"])
        if not np.isfinite(vwap):
            continue
        hi, lo, cl = float(row.high), float(row.low), float(row.close)
        if d == 1:
            if lo <= vwap:
                touched = True
            if touched and cl > vwap:
                return True
        else:
            if hi >= vwap:
                touched = True
            if touched and cl < vwap:
                return True
    return False


def vwap_retest_entry(
    market: pd.DataFrame,
    bos_i: int,
    direction: str,
    *,
    tol_atr: float,
    max_wait: int,
) -> tuple[bool, int, float]:
    """V5: after B1 at bos_i, wait for causal VWAP retest + continuation."""
    d = 1 if str(direction).lower() == "long" else -1
    atr = float(market.iloc[bos_i].get("atr", np.nan))
    if not np.isfinite(atr) or atr <= 0:
        atr = float((market.iloc[bos_i].high - market.iloc[bos_i].low))
    for j in range(bos_i + 1, min(len(market), bos_i + 1 + max_wait)):
        row = market.iloc[j]
        vwap = float(row["vwap"])
        if not np.isfinite(vwap):
            continue
        tol = tol_atr * atr
        hi, lo, cl = float(row.high), float(row.low), float(row.close)
        if d == 1:
            touched = lo <= vwap + tol
            holds = cl >= vwap
            if touched and holds:
                return True, j, cl
        else:
            touched = hi >= vwap - tol
            holds = cl <= vwap
            if touched and holds:
                return True, j, cl
    return False, -1, np.nan
