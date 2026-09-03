"""Causal feature engineering for Phase 26."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase16.indicators import add_base_indicators, is_in_session
from phase20.session_levels import prepare_session_liquidity_frame

from .config import NQ_DATA_PATHS, PIVOT_LEFT, RESEARCH_END, RESEARCH_START


def load_market(config: FrozenConfig = FrozenConfig()) -> pd.DataFrame:
    frames = [load_ohlcv_csv(p, exchange_timezone=config.exchange_timezone) for p in NQ_DATA_PATHS]
    market = pd.concat(frames).sort_index()
    market = market[~market.index.duplicated(keep="last")]
    market = add_base_indicators(market, config)
    tz = config.exchange_timezone
    start = pd.Timestamp(RESEARCH_START, tz=tz)
    end = pd.Timestamp(RESEARCH_END, tz=tz)
    market = market.loc[(market.index >= start) & (market.index < end)]
    return market


def _causal_swing_distance(market: pd.DataFrame, left: int = PIVOT_LEFT) -> pd.DataFrame:
    high = market["high"]
    low = market["low"]
    close = market["close"]
    pivot_high = high.shift(1).rolling(left, min_periods=left).max()
    pivot_low = low.shift(1).rolling(left, min_periods=left).min()
    confirmed_high = high.shift(left + 1).rolling(left, min_periods=1).max()
    confirmed_low = low.shift(left + 1).rolling(left, min_periods=1).min()
    out = pd.DataFrame(index=market.index)
    atr = market["atr"].replace(0, np.nan)
    out["dist_swing_high_atr"] = (confirmed_high - close) / atr
    out["dist_swing_low_atr"] = (close - confirmed_low) / atr
    roll_high = high.shift(1).rolling(48, min_periods=12).max()
    roll_low = low.shift(1).rolling(48, min_periods=12).min()
    roll_range = (roll_high - roll_low).replace(0, np.nan)
    out["range_position"] = (close - roll_low) / roll_range
    out["range_width_atr"] = roll_range / atr
    out["breakout_up_atr"] = (close - roll_high) / atr
    out["breakout_down_atr"] = (roll_low - close) / atr
    prev_high = high.shift(1).rolling(48, min_periods=1).max()
    prev_low = low.shift(1).rolling(48, min_periods=1).min()
    out["bars_since_high"] = (close < prev_high).groupby((close >= prev_high).cumsum()).cumcount()
    out["bars_since_low"] = (close > prev_low).groupby((close <= prev_low).cumsum()).cumcount()
    return out


def build_features(market: pd.DataFrame, config: FrozenConfig = FrozenConfig()) -> pd.DataFrame:
    df = pd.DataFrame(index=market.index)
    atr = market["atr"].replace(0, np.nan)
    rng = (market["high"] - market["low"]).replace(0, np.nan)
    body = (market["close"] - market["open"]).abs()

    df["body_atr"] = body / atr
    df["range_atr"] = rng / atr
    df["body_range"] = body / rng
    df["close_location"] = (market["close"] - market["low"]) / rng
    df["upper_wick"] = (market["high"] - np.maximum(market["open"], market["close"])) / rng
    df["lower_wick"] = (np.minimum(market["open"], market["close"]) - market["low"]) / rng
    df["ret_1_atr"] = market["close"].diff() / atr
    df["ret_3_atr"] = (market["close"] - market["close"].shift(3)) / atr
    df["ret_6_atr"] = (market["close"] - market["close"].shift(6)) / atr
    df["accel_atr"] = df["ret_1_atr"] - df["ret_1_atr"].shift(1)
    overlap = np.minimum(market["high"], market["high"].shift(1)) - np.maximum(market["low"], market["low"].shift(1))
    df["overlap_ratio"] = overlap.clip(lower=0) / rng
    direction = np.sign(market["close"] - market["open"]).replace(0, np.nan)
    df["consec_dir"] = direction.groupby((direction != direction.shift()).cumsum()).cumcount() + 1
    df.loc[direction.isna(), "consec_dir"] = np.nan

    struct = _causal_swing_distance(market)
    df = df.join(struct)

    atr6 = market["atr"].ewm(alpha=1 / 6, adjust=False).mean()
    atr72 = market["atr"].ewm(alpha=1 / 72, adjust=False).mean()
    df["atr_ratio_6_72"] = atr6 / atr72
    norm_atr = market["atr"] / market["close"]
    hist = norm_atr.shift(1).rolling(5000, min_periods=1000)
    df["atr_percentile"] = norm_atr.rank(pct=True)
    df["range_percentile"] = (rng / market["close"]).rank(pct=True)
    rv = market["close"].pct_change().rolling(12).std()
    df["realized_vol"] = rv
    df["vol_percentile"] = rv.rank(pct=True)
    df["compression"] = (df["range_atr"] < df["range_atr"].shift(1).rolling(48).quantile(0.25)).astype(int)
    df["expansion"] = (df["range_atr"] > df["range_atr"].shift(1).rolling(48).quantile(0.75)).astype(int)

    vol = market["volume"].astype(float)
    vol_mean = vol.shift(1).rolling(288, min_periods=72).mean()
    vol_std = vol.shift(1).rolling(288, min_periods=72).std().replace(0, np.nan)
    df["volume_z"] = (vol - vol_mean) / vol_std
    df["volume_percentile"] = vol.rank(pct=True)
    df["vol_accel"] = vol / vol.shift(1)
    df["disp_per_volume"] = (rng / vol.replace(0, np.nan)).rank(pct=True)

    idx = market.index
    df["minute_of_day"] = idx.hour * 60 + idx.minute
    df["minutes_from_open"] = df["minute_of_day"] - (9 * 60 + 30)
    df["day_of_week"] = idx.dayofweek
    df["is_rth"] = pd.Series([is_in_session(ts, "0930-1600") for ts in idx], index=idx).astype(int)

    liq = prepare_session_liquidity_frame(market, config)
    for name, col in (("pdh", "pdh"), ("pdl", "pdl"), ("onh", "onh"), ("onl", "onl"), ("session_open", "session_open")):
        if col in liq.columns:
            df[f"dist_{name}_atr"] = (market["close"] - liq[col]).abs() / atr

    df["atr_frozen"] = market["atr"]
    df["close_frozen"] = market["close"]
    return df
