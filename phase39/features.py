"""Causal entry-time features for frozen signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import pine_ema, pine_sma
from phase35.features import build_features


def _build_extended_features(market: pd.DataFrame) -> pd.DataFrame:
    """Vectorized causal features for every bar (entry-time safe)."""
    df = market.copy()
    atr = df["atr"].astype(float)
    atr_s = atr
    atr_long = pine_sma(atr_s, 50)
    rng = df["high"] - df["low"]

    ext = pd.DataFrame(index=df.index)
    for w in (3, 5, 8):
        past_rng = rng.shift(1).rolling(w, min_periods=w).mean()
        ext[f"avg_range_{w}_atr"] = past_rng / atr.replace(0, np.nan)
    ext["atr_short_long_ratio"] = atr_s / atr_long.replace(0, np.nan)
    ext["realized_vol_8"] = df["close"].pct_change().shift(1).rolling(8).std()
    ext["inside_bar_density_8"] = (
        ((df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1)))
        .shift(1)
        .rolling(8)
        .mean()
    )
    alt = (df["close"].diff().shift(1) > 0).astype(int).diff().abs().rolling(8).sum()
    ext["alternating_bars_8"] = alt
    overlap = (
        (df["high"].shift(1) >= df["low"]) & (df["low"].shift(1) <= df["high"])
    ).astype(float).shift(1).rolling(5).mean()
    ext["overlap_density_5"] = overlap

    # Session expanding high/low/travel within calendar day (causal)
    dates = pd.Series([t.date() for t in df.index], index=df.index)
    sess_hi = df.groupby(dates)["high"].expanding().max().reset_index(level=0, drop=True)
    sess_lo = df.groupby(dates)["low"].expanding().min().reset_index(level=0, drop=True)
    ext["dist_session_high_atr"] = (sess_hi - df["close"]) / atr.replace(0, np.nan)
    ext["dist_session_low_atr"] = (df["close"] - sess_lo) / atr.replace(0, np.nan)
    ext["session_travel_atr"] = (sess_hi - sess_lo) / atr.replace(0, np.nan)

    close = df["close"].astype(float)
    ext["pre_entry_move_3"] = close - close.shift(3)
    ext["pre_entry_move_5"] = close - close.shift(5)
    abs_move_5 = close.diff().abs().rolling(5).sum()
    ext["pre_entry_efficiency_5"] = ext["pre_entry_move_5"] / abs_move_5.replace(0, np.nan)
    ext["atr"] = atr

    return ext


def build_signal_features(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Attach causal features known at entry bar only."""
    base = build_features(market)
    ext = _build_extended_features(market)
    all_feats = base.join(ext)

    sig = signals.copy()
    sig["marker_bar_timestamp"] = pd.to_datetime(sig["marker_bar_timestamp"], utc=True)
    if "atr" in sig.columns:
        sig = sig.rename(columns={"atr": "signal_atr"})
    merged = sig.merge(
        all_feats,
        left_on="marker_bar_timestamp",
        right_index=True,
        how="left",
    )

    direction = np.where(merged["direction"].astype(str).str.lower() == "long", 1, -1)
    if "atr" in merged.columns:
        atr = merged["atr"].astype(float).values
    elif "signal_atr" in merged.columns:
        atr = merged["signal_atr"].astype(float).values
    else:
        atr = market["atr"].reindex(merged["marker_bar_timestamp"]).astype(float).values

    merged["pre_entry_move_3_atr"] = merged["pre_entry_move_3"].astype(float).values * direction / np.where(atr > 0, atr, np.nan)
    merged["pre_entry_move_5_atr"] = merged["pre_entry_move_5"].astype(float).values * direction / np.where(atr > 0, atr, np.nan)
    merged["day_of_week"] = merged["marker_bar_timestamp"].dt.dayofweek

    if "source_displacement_midpoint" in merged.columns:
        mid = merged["source_displacement_midpoint"].astype(float)
        merged["dist_from_disp_mid_atr"] = (merged["entry_price"].astype(float) - mid).abs() / np.where(atr > 0, atr, np.nan)
    else:
        merged["dist_from_disp_mid_atr"] = np.nan

    if "bos_level" in merged.columns:
        bos = merged["bos_level"].astype(float)
        merged["dist_from_bos_atr"] = (merged["entry_price"].astype(float) - bos) * direction / np.where(atr > 0, atr, np.nan)
    else:
        merged["dist_from_bos_atr"] = np.nan

    drop_cols = {"pre_entry_move_3", "pre_entry_move_5", "entry_price", "stop", "target", "signal_type", "direction", "architecture"}
    merged = merged.drop(columns=[c for c in drop_cols if c in merged.columns])
    return merged
