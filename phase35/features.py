"""Causal feature engineering for Phase 35 — no future information."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session, pine_ema, pine_sma, session_bucket

from .config import RTH_SESSION


def _close_location(df: pd.DataFrame) -> pd.Series:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    return ((df["close"] - df["low"]) / rng).rename("close_loc")


def _wick_ratios(df: pd.DataFrame) -> pd.DataFrame:
    rng = (df["high"] - df["low"]).replace(0, np.nan)
    body_top = df[["open", "close"]].max(axis=1)
    body_bot = df[["open", "close"]].min(axis=1)
    return pd.DataFrame(
        {
            "upper_wick_ratio": ((df["high"] - body_top) / rng).astype(float),
            "lower_wick_ratio": ((body_bot - df["low"]) / rng).astype(float),
        },
        index=df.index,
    )


def _consecutive_direction(close: pd.Series) -> pd.DataFrame:
    up = (close.diff() > 0).astype(int)
    down = (close.diff() < 0).astype(int)
    consec_up = up.groupby((up != up.shift()).cumsum()).cumsum()
    consec_down = down.groupby((down != down.shift()).cumsum()).cumsum()
    return pd.DataFrame({"consec_up": consec_up, "consec_down": consec_down}, index=close.index)


def build_features(market: pd.DataFrame) -> pd.DataFrame:
    df = market.copy()
    atr = df["atr"].astype(float)
    body = (df["close"] - df["open"]).abs()
    rng = (df["high"] - df["low"]).replace(0, np.nan)

    feats = pd.DataFrame(index=df.index)
    feats["body_atr"] = body / atr
    feats["body_range"] = body / rng
    wicks = _wick_ratios(df)
    feats["upper_wick_ratio"] = wicks["upper_wick_ratio"]
    feats["lower_wick_ratio"] = wicks["lower_wick_ratio"]
    feats["close_loc"] = _close_location(df)
    feats["range_atr"] = rng / atr
    vol_sma = pine_sma(df["volume"].astype(float), 20)
    feats["rel_volume"] = df["volume"].astype(float) / vol_sma

    for n in (1, 2, 3, 4, 8):
        feats[f"ret_{n}"] = df["close"].pct_change(n)
    feats["mom_accel"] = feats["ret_1"] - feats["ret_1"].shift(1)

    consec = _consecutive_direction(df["close"])
    feats["consec_up"] = consec["consec_up"]
    feats["consec_down"] = consec["consec_down"]

    # Structure — causal rolling extrema (past bars only)
    for w in (8, 16, 32):
        past_high = df["high"].shift(1).rolling(w, min_periods=w).max()
        past_low = df["low"].shift(1).rolling(w, min_periods=w).min()
        feats[f"dist_high_{w}_atr"] = (df["close"] - past_high) / atr
        feats[f"dist_low_{w}_atr"] = (past_low - df["close"]) / atr
        feats[f"break_high_{w}"] = (df["close"] > past_high).astype(float)
        feats[f"break_low_{w}"] = (df["close"] < past_low).astype(float)

    # Pullback / impulse
    feats["impulse_3bar"] = (df["close"] - df["close"].shift(3)).abs() / atr
    feats["pullback_from_high_8"] = (df["high"].shift(1).rolling(8, min_periods=8).max() - df["close"]) / atr
    feats["pullback_from_low_8"] = (df["close"] - df["low"].shift(1).rolling(8, min_periods=8).min()) / atr

    # Displacement-style (same as Phase 31 definition — causal)
    avg_body = pine_sma(body, 20)
    feats["disp_long"] = (
        (body > 1.5 * avg_body) & (feats["close_loc"] >= 0.80)
    ).astype(float)
    feats["disp_short"] = (
        (body > 1.5 * avg_body) & (feats["close_loc"] <= 0.20)
    ).astype(float)

    # Midpoint reclaim failure proxy (causal, 4-bar lookback for reclaim detection uses only past disp bar)
    mid = (df["high"] + df["low"]) / 2.0
    feats["mid_reclaim_up"] = ((df["close"] > mid) & (df["close"].shift(1) <= mid.shift(1))).astype(float)
    feats["mid_reclaim_down"] = ((df["close"] < mid) & (df["close"].shift(1) >= mid.shift(1))).astype(float)

    # Trend
    ema8 = pine_ema(df["close"], 8)
    ema21 = pine_ema(df["close"], 21)
    feats["ema8_slope"] = ema8.diff() / atr
    feats["price_vs_ema8"] = (df["close"] - ema8) / atr
    feats["price_vs_ema21"] = (df["close"] - ema21) / atr
    feats["trend_agree"] = np.sign(feats["price_vs_ema8"]) == np.sign(feats["price_vs_ema21"])

    # Volatility regime
    atr_pct = atr.rolling(100, min_periods=100).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
    feats["atr_percentile"] = atr_pct
    feats["atr_expansion"] = atr / atr.shift(5)

    # Session
    feats["session_bucket"] = df.index.map(session_bucket).astype(float)
    open_min = 9 * 60 + 30
    feats["minutes_since_open"] = df.index.map(lambda ts: ts.hour * 60 + ts.minute - open_min).astype(float)

    feats["timestamp"] = df.index
    feats["bar_index"] = np.arange(len(df))
    feats["in_rth"] = [is_in_session(ts, RTH_SESSION) for ts in df.index]

    return feats
