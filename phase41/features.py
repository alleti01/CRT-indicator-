"""Causal reversal features at decision bar."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session, pine_ema, pine_sma, session_bucket
from phase35.features import build_features

from .config import RTH_SESSION


def build_reversal_features(market: pd.DataFrame) -> pd.DataFrame:
    base = build_features(market)
    df = market.copy()
    atr = df["atr"].astype(float)
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    ext = pd.DataFrame(index=df.index)

    ema8 = pine_ema(df["close"], 8)
    ema20 = pine_ema(df["close"], 20)
    ext["dist_ema8_atr"] = (df["close"] - ema8) / atr
    ext["dist_ema20_atr"] = (df["close"] - ema20) / atr
    ext["ema8_slope"] = ema8.diff() / atr
    ext["ret_3_atr"] = (df["close"] - df["close"].shift(3)) / atr
    ext["ret_6_atr"] = (df["close"] - df["close"].shift(6)) / atr
    ext["range_expansion"] = rng / rng.shift(1).rolling(5).mean()
    ext["atr_expansion"] = atr / pine_sma(atr, 20)
    ext["body_contract"] = (df["close"] - df["open"]).abs() / (df["close"] - df["open"]).abs().shift(1)
    ext["failed_new_low"] = (df["low"] >= df["low"].shift(1)).astype(float)
    ext["failed_new_high"] = (df["high"] <= df["high"].shift(1)).astype(float)
    ext["reclaim_prior_mid"] = (df["close"] > (df["high"].shift(1) + df["low"].shift(1)) / 2).astype(float)
    ext["reclaim_prior_close"] = (df["close"] > df["close"].shift(1)).astype(float)
    ext["engulfing_bull"] = ((df["close"] > df["open"]) & (df["close"] > df["high"].shift(1)) & (df["open"] < df["low"].shift(1))).astype(float)
    ext["engulfing_bear"] = ((df["close"] < df["open"]) & (df["close"] < df["low"].shift(1)) & (df["open"] > df["high"].shift(1))).astype(float)
    ext["outside_bar"] = ((df["high"] > df["high"].shift(1)) & (df["low"] < df["low"].shift(1))).astype(float)
    ext["micro_higher_low"] = (df["low"] > df["low"].shift(1)).astype(float)
    ext["micro_lower_high"] = (df["high"] < df["high"].shift(1)).astype(float)
    ext["atr_percentile"] = atr.rolling(100, min_periods=20).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)

    dates = pd.Series([t.date() for t in df.index], index=df.index)
    sess_hi = df.groupby(dates)["high"].expanding().max().reset_index(level=0, drop=True)
    sess_lo = df.groupby(dates)["low"].expanding().min().reset_index(level=0, drop=True)
    ext["dist_session_high_atr"] = (sess_hi - df["close"]) / atr
    ext["dist_session_low_atr"] = (df["close"] - sess_lo) / atr

    ext["session_bucket"] = [session_bucket(t) for t in df.index]
    ext["minutes_since_open"] = np.nan  # placeholder; session_bucket captures coarse timing

    for col in list(ext.columns):
        if col in base.columns:
            ext = ext.drop(columns=[col])
    return base.join(ext)


def features_at_timestamps(feats: pd.DataFrame, timestamps: pd.Series) -> pd.DataFrame:
    ts = pd.to_datetime(timestamps, utc=True)
    rows = []
    for t in ts:
        if t in feats.index:
            rows.append(feats.loc[t].to_dict())
        else:
            rows.append({})
    out = pd.DataFrame(rows)
    out.insert(0, "timestamp", ts.values)
    return out
