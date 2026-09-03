"""Prior-day RTH market profile construction from 5m bars."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig
from phase16.indicators import add_base_indicators, is_in_session
from phase16.resample import cme_session_date

from .config import PROFILE_TICK, RTH_SESSION, VALUE_AREA_PCT


def minute_of_day(timestamp: pd.Timestamp) -> int:
    return int(timestamp.hour * 60 + timestamp.minute)


def rth_time_bucket(timestamp: pd.Timestamp) -> str:
    minute = minute_of_day(timestamp)
    if minute < 10 * 60 + 30:
        return "RTH_0930_1030"
    if minute < 12 * 60:
        return "RTH_1030_1200"
    if minute < 14 * 60:
        return "RTH_1200_1400"
    if minute < 16 * 60:
        return "RTH_1400_1600"
    return "OUTSIDE_RTH"


def distribute_bar_volume(low: float, high: float, volume: float, tick: float = PROFILE_TICK) -> Dict[float, float]:
    if not np.isfinite(volume) or volume <= 0 or not np.isfinite(low) or not np.isfinite(high):
        return {}
    low_bin = math.floor(low / tick) * tick
    high_bin = math.ceil(high / tick) * tick
    if high_bin < low_bin:
        low_bin, high_bin = high_bin, low_bin
    levels = np.arange(low_bin, high_bin + tick / 2.0, tick)
    if len(levels) == 0:
        return {round(low_bin, 2): float(volume)}
    share = float(volume) / float(len(levels))
    return {round(float(level), 2): share for level in levels}


def build_volume_profile(rth_bars: pd.DataFrame, tick: float = PROFILE_TICK) -> Optional[Dict[str, float]]:
    volume_at_price: Dict[float, float] = {}
    for _, bar in rth_bars.iterrows():
        for price, share in distribute_bar_volume(float(bar.low), float(bar.high), float(bar.volume), tick).items():
            volume_at_price[price] = volume_at_price.get(price, 0.0) + share
    if not volume_at_price:
        return None
    prices = sorted(volume_at_price.keys())
    volumes = np.array([volume_at_price[p] for p in prices], dtype=float)
    total = float(volumes.sum())
    if total <= 0:
        return None
    poc_idx = int(np.argmax(volumes))
    poc = float(prices[poc_idx])
    low_idx = high_idx = poc_idx
    captured = float(volumes[poc_idx])
    while captured / total < VALUE_AREA_PCT and (low_idx > 0 or high_idx < len(prices) - 1):
        below = float(volumes[low_idx - 1]) if low_idx > 0 else -1.0
        above = float(volumes[high_idx + 1]) if high_idx < len(prices) - 1 else -1.0
        if above >= below and high_idx < len(prices) - 1:
            high_idx += 1
            captured += float(volumes[high_idx])
        elif low_idx > 0:
            low_idx -= 1
            captured += float(volumes[low_idx])
        else:
            break
    val = float(prices[low_idx])
    vah = float(prices[high_idx])
    day_high = float(rth_bars["high"].max())
    day_low = float(rth_bars["low"].min())
    day_close = float(rth_bars["close"].iloc[-1])
    width = vah - val
    if width <= 0:
        shape = "UNKNOWN"
    else:
        poc_position = (poc - day_low) / max(day_high - day_low, tick)
        if poc_position >= 0.66:
            shape = "UPPER_HEAVY"
        elif poc_position <= 0.34:
            shape = "LOWER_HEAVY"
        else:
            shape = "BALANCED"
    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "value_width": width,
        "day_high": day_high,
        "day_low": day_low,
        "day_close": day_close,
        "total_volume": total,
        "profile_shape": shape,
        "poc_vs_day_range": (poc - day_low) / max(day_high - day_low, tick),
        "close_vs_value": "ABOVE" if day_close > vah else ("BELOW" if day_close < val else "INSIDE"),
    }


def classify_value_migration(current: Dict[str, float], previous: Dict[str, float]) -> str:
    if previous is None:
        return "OVERLAP_FLAT"
    if current["val"] > previous["vah"]:
        return "VALUE_UP"
    if current["vah"] < previous["val"]:
        return "VALUE_DOWN"
    return "OVERLAP_FLAT"


def build_daily_profiles(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.sort_index().copy()
    data = add_base_indicators(data, config)
    data["cme_session_date"] = cme_session_date(data.index)
    data["in_rth"] = [is_in_session(ts, RTH_SESSION) for ts in data.index]
    rows: List[dict] = []
    for session_date, group in data.groupby("cme_session_date"):
        rth = group.loc[group["in_rth"]]
        if rth.empty:
            continue
        profile = build_volume_profile(rth)
        if profile is None:
            continue
        atr = float(rth["atr"].iloc[-1]) if np.isfinite(rth["atr"].iloc[-1]) else float("nan")
        rows.append(
            {
                "session_date": session_date,
                "rth_start": rth.index[0],
                "rth_end": rth.index[-1],
                "poc": profile["poc"],
                "vah": profile["vah"],
                "val": profile["val"],
                "value_width": profile["value_width"],
                "value_width_atr": profile["value_width"] / atr if np.isfinite(atr) and atr > 0 else np.nan,
                "day_high": profile["day_high"],
                "day_low": profile["day_low"],
                "day_close": profile["day_close"],
                "profile_shape": profile["profile_shape"],
                "poc_vs_day_range": profile["poc_vs_day_range"],
                "close_vs_value": profile["close_vs_value"],
                "rth_atr": atr,
            }
        )
    profiles = pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)
    profiles["poc_delta"] = profiles["poc"].diff()
    profiles["vah_delta"] = profiles["vah"].diff()
    profiles["val_delta"] = profiles["val"].diff()
    profiles["poc_delta_atr"] = profiles["poc_delta"] / profiles["rth_atr"]
    prev_records = profiles.shift(1).to_dict("records")
    profiles["value_migration"] = [
        classify_value_migration(cur, prev if isinstance(prev, dict) and pd.notna(prev.get("poc")) else None)
        for cur, prev in zip(profiles.to_dict("records"), prev_records)
    ]
    if len(profiles) >= 20:
        profiles["value_width_quartile"] = pd.qcut(
            profiles["value_width_atr"].rank(method="first"),
            4,
            labels=["Q1", "Q2", "Q3", "Q4"],
            duplicates="drop",
        )
    else:
        profiles["value_width_quartile"] = "ALL"
    return profiles


def attach_prior_profile_to_bars(frame: pd.DataFrame, profiles: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.sort_index().copy()
    if "atr" not in data.columns:
        data = add_base_indicators(data, config)
    data["cme_session_date"] = cme_session_date(data.index)
    data["in_rth"] = [is_in_session(ts, RTH_SESSION) for ts in data.index]
    data["rth_time_bucket"] = [rth_time_bucket(ts) if is_in_session(ts, RTH_SESSION) else "OUTSIDE_RTH" for ts in data.index]
    profile_map = profiles.set_index("session_date")
    prior_dates = profile_map.index.to_series().shift(1)
    lookup = dict(zip(profile_map.index, prior_dates))
    data["prior_profile_session"] = data["cme_session_date"].map(lookup)

    for column in (
        "poc",
        "vah",
        "val",
        "value_width",
        "value_width_atr",
        "value_migration",
        "profile_shape",
        "value_width_quartile",
    ):
        data[f"prior_{column}"] = data["prior_profile_session"].map(profile_map[column].to_dict())

    open_rows = []
    for session_date, group in data.loc[data["in_rth"]].groupby("cme_session_date"):
        first = group.iloc[0]
        if not np.isfinite(first.get("prior_vah", np.nan)):
            continue
        open_price = float(first["open"])
        vah = float(first["prior_vah"])
        val = float(first["prior_val"])
        poc = float(first["prior_poc"])
        atr = float(first["atr"]) if np.isfinite(first["atr"]) and first["atr"] > 0 else np.nan
        if open_price > vah:
            loc = "ABOVE_VAH"
        elif open_price < val:
            loc = "BELOW_VAL"
        else:
            loc = "INSIDE_VALUE"
        open_rows.append(
            {
                "cme_session_date": session_date,
                "open_location": loc,
                "open_dist_vah_atr": (open_price - vah) / atr if np.isfinite(atr) else np.nan,
                "open_dist_val_atr": (open_price - val) / atr if np.isfinite(atr) else np.nan,
                "open_dist_poc_atr": (open_price - poc) / atr if np.isfinite(atr) else np.nan,
            }
        )
    open_df = pd.DataFrame(open_rows).set_index("cme_session_date")
    for column in open_df.columns:
        data[column] = data["cme_session_date"].map(open_df[column].to_dict())
    data["open_location"] = data["open_location"].fillna("UNKNOWN")
    return data
