"""Causal entry-time quality features for frozen Phase 40 signals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import pine_ema, session_bucket
from phase39.features import build_signal_features

from .config import IMPULSE_THRESHOLD

FEATURE_COLS = [
    "impulse_3bar",
    "impulse_margin",
    "body_atr",
    "range_atr",
    "body_range",
    "close_loc",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "rel_volume",
    "atr_percentile",
    "atr_expansion",
    "atr_short_long_ratio",
    "ret_1_atr",
    "ret_2_atr",
    "ret_3_atr",
    "ret_4_atr",
    "ret_6_atr",
    "mom_accel_atr",
    "directional_efficiency",
    "pre_entry_move_3_atr",
    "pre_entry_move_5_atr",
    "pre_entry_efficiency_5",
    "price_vs_ema8",
    "price_vs_ema21",
    "ema8_slope",
    "trend_agree",
    "trend_aligned",
    "countertrend",
    "dist_high_8_atr",
    "dist_low_8_atr",
    "dist_high_16_atr",
    "dist_low_16_atr",
    "dist_session_high_atr",
    "dist_session_low_atr",
    "session_travel_atr",
    "overlap_density_5",
    "alternating_bars_8",
    "inside_bar_density_8",
    "avg_range_3_atr",
    "avg_range_5_atr",
    "dist_from_bos_atr",
    "dist_from_disp_mid_atr",
    "disp_strength_atr",
    "reclaim_strength_atr",
    "retest_depth_atr",
    "rejection_wick",
    "candidate_age_bars",
    "bars_disp_to_entry",
    "bars_reclaim_to_entry",
    "minutes_since_open",
    "day_of_week",
]


def _dir_norm(series: pd.Series, direction: pd.Series, atr: pd.Series) -> pd.Series:
    d = np.where(direction.astype(str).str.lower() == "long", 1, -1)
    return series.astype(float).values * d / np.where(atr.astype(float).values > 0, atr.astype(float).values, np.nan)


def build_quality_features(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    base = build_signal_features(signals, market)
    df = signals.copy()
    df["marker_bar_timestamp"] = pd.to_datetime(df["marker_bar_timestamp"], utc=True)
    merged = df.merge(base, on=["signal_id", "marker_bar_timestamp"], how="left", suffixes=("", "_feat"))

    atr = merged["atr"].astype(float) if "atr" in merged.columns else merged.get("signal_atr", pd.Series(np.nan, index=merged.index)).astype(float)
    direction = merged["direction"]

    merged["impulse_margin"] = merged["impulse_3bar"].astype(float) - IMPULSE_THRESHOLD
    for n in (1, 2, 3, 4, 6):
        col = f"ret_{n}"
        if col in merged.columns:
            merged[f"ret_{n}_atr"] = _dir_norm(merged[col] * atr, direction, atr)
    if "mom_accel" in merged.columns:
        merged["mom_accel_atr"] = _dir_norm(merged["mom_accel"] * atr, direction, atr)

    # Trend alignment with signal direction
    if "price_vs_ema8" in merged.columns:
        dsign = np.where(direction.astype(str).str.lower() == "long", 1, -1)
        merged["trend_aligned"] = (np.sign(merged["price_vs_ema8"].astype(float)) == dsign).astype(float)
        merged["countertrend"] = 1.0 - merged["trend_aligned"]

    # Rejection wick aligned with signal
    merged["rejection_wick"] = np.where(
        direction.astype(str).str.lower() == "long",
        merged.get("lower_wick_ratio", 0),
        merged.get("upper_wick_ratio", 0),
    )

    pos = {ts: i for i, ts in enumerate(market.index)}

    def _bar_delta(ts_col: str) -> pd.Series:
        out = []
        for row in merged.itertuples(index=False):
            ts = pd.Timestamp(getattr(row, "marker_bar_timestamp"))
            ref = getattr(row, ts_col, None)
            if pd.isna(ref) or ts not in pos:
                out.append(np.nan)
                continue
            ref_ts = pd.Timestamp(ref)
            if ref_ts in pos:
                out.append(pos[ts] - pos[ref_ts])
            else:
                out.append(np.nan)
        return pd.Series(out, index=merged.index)

    if "source_displacement_time" in merged.columns:
        merged["bars_disp_to_entry"] = _bar_delta("source_displacement_time")
    if "bos_or_reclaim_time" in merged.columns:
        merged["bars_reclaim_to_entry"] = _bar_delta("bos_or_reclaim_time")
    if "retest_time" in merged.columns:
        merged["retest_depth_atr"] = _bar_delta("retest_time")

    # Displacement / reclaim strength
    if "source_displacement_high" in merged.columns and "source_displacement_low" in merged.columns:
        disp_rng = (merged["source_displacement_high"].astype(float) - merged["source_displacement_low"].astype(float))
        merged["disp_strength_atr"] = disp_rng / np.where(atr > 0, atr, np.nan)
    if "reclaim_level" in merged.columns:
        merged["reclaim_strength_atr"] = (merged["entry_price"].astype(float) - merged["reclaim_level"].astype(float)).abs() / np.where(atr > 0, atr, np.nan)

    merged["minutes_since_open"] = merged["marker_bar_timestamp"].map(
        lambda t: (t.hour - 9) * 60 + (t.minute - 30) if hasattr(t, "hour") else np.nan
    )
    merged["day_of_week"] = merged["marker_bar_timestamp"].dt.dayofweek

    if "candidate_id" in merged.columns:
        merged["candidate_age_bars"] = merged.groupby("candidate_id").cumcount()

    return merged


def available_feature_cols(df: pd.DataFrame) -> list[str]:
    return [c for c in FEATURE_COLS if c in df.columns and df[c].notna().sum() > 50]
