"""Build causal B1 price-action feature dataset."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .structure import causal_swing_levels, count_touches, liquidity_sweep_before, structure_age_bars


def _bar_index(market: pd.DataFrame, ts) -> int:
    ts = pd.Timestamp(ts).tz_convert(market.index.tz)
    if ts in market.index:
        return int(market.index.get_loc(ts))
    return int(market.index.searchsorted(ts, side="left"))


def extract_b1_bar_features(
    market: pd.DataFrame,
    entry_i: int,
    direction: str,
    structure_level: float,
    swing_bar: int,
    actionable_i: int,
) -> dict:
    bar = market.iloc[entry_i]
    hi = float(bar.high)
    lo = float(bar.low)
    cl = float(bar.close)
    op = float(bar.open)
    rng = hi - lo
    atr = float(bar.get("atr", np.nan))
    if not np.isfinite(atr) or atr <= 0:
        atr = max(rng, 1e-9)
    long = str(direction).lower() == "long"
    body = abs(cl - op)
    upper_wick = hi - max(op, cl)
    lower_wick = min(op, cl) - lo

    if long:
        break_strength = cl - structure_level if np.isfinite(structure_level) else np.nan
        close_quality = (cl - lo) / rng if rng > 0 else np.nan
        opposing_wick_ratio = upper_wick / rng if rng > 0 else np.nan
    else:
        break_strength = structure_level - cl if np.isfinite(structure_level) else np.nan
        close_quality = (hi - cl) / rng if rng > 0 else np.nan
        opposing_wick_ratio = lower_wick / rng if rng > 0 else np.nan

    hi_a = market["high"].astype(float).values
    lo_a = market["low"].astype(float).values
    sh, sl, sh_i, sl_i = causal_swing_levels(hi_a, lo_a, entry_i)
    ref_level = sl if long else sh
    ref_bar = sl_i if long else sh_i
    swept = liquidity_sweep_before(hi_a, lo_a, actionable_i, entry_i, direction, ref_level, ref_bar)
    touches = count_touches(hi_a, lo_a, structure_level, max(0, entry_i - 30), entry_i - 1, long=not long) if np.isfinite(structure_level) else 0

    return {
        "structure_level": structure_level,
        "structure_age_bars": structure_age_bars(entry_i, swing_bar),
        "break_strength": break_strength,
        "break_strength_atr": break_strength / atr if np.isfinite(break_strength) else np.nan,
        "range_atr": rng / atr if atr > 0 else np.nan,
        "body_atr": body / atr if atr > 0 else np.nan,
        "body_range_ratio": body / rng if rng > 0 else np.nan,
        "close_quality": close_quality,
        "upper_wick_ratio": upper_wick / rng if rng > 0 else np.nan,
        "lower_wick_ratio": lower_wick / rng if rng > 0 else np.nan,
        "opposing_wick_ratio": opposing_wick_ratio,
        "local_liquidity_sweep": int(swept),
        "structure_touches": touches,
        "atr_1m": atr,
        "retest_state": "immediate",
        "follow_through_state": "none",
    }


def features_from_control_row(row: pd.Series, market: pd.DataFrame) -> dict | None:
    act = pd.Timestamp(row["actionable_timestamp"]).tz_convert(market.index.tz)
    act_i = _bar_index(market, act)
    delay = float(row["B_delay_min"])
    entry_i = _bar_index(market, act + pd.Timedelta(minutes=delay))
    if entry_i < 0 or entry_i >= len(market):
        return None
    hi_a = market["high"].astype(float).values
    lo_a = market["low"].astype(float).values
    sh, sl, sh_i, sl_i = causal_swing_levels(hi_a, lo_a, entry_i)
    long = str(row["direction"]).lower() == "long"
    struct = sh if long else sl
    swing_bar = sh_i if long else sl_i
    feat = extract_b1_bar_features(market, entry_i, row["direction"], struct, swing_bar, act_i)
    return {
        "signal_id": row["signal_id"],
        "marker_bar_timestamp": row["marker_bar_timestamp"],
        "direction": row["direction"],
        "signal_type": row["signal_type"],
        "confidence": row["confidence"],
        "phase44_class": row["confidence"],
        "setup_type": row["signal_type"],
        "fold": row.get("fold"),
        "train_selected_b1_window": row.get("selected_window"),
        "b1_timestamp": market.index[entry_i],
        "b1_delay_min": delay,
        "entry_price": row["B_entry_price"],
        "entry_i": entry_i,
        "stop": row["stop"],
        "target": row["target"],
        "final_r": row["B_net_R"],
        "mae": row["B_MAE_R"],
        "mfe": row["B_MFE_R"],
        "wrong_direction": row["B_wrong_direction"],
        **feat,
    }


def features_from_dataset_row(row: pd.Series, market: pd.DataFrame, win: int) -> dict | None:
    prefix = f"B1_w{win}"
    if not row.get(f"{prefix}_filled"):
        return None
    act = pd.Timestamp(row["actionable_timestamp"]).tz_convert(market.index.tz)
    act_i = _bar_index(market, act)
    delay = float(row[f"{prefix}_delay_min"])
    entry_i = _bar_index(market, act + pd.Timedelta(minutes=delay))
    if entry_i < 0 or entry_i >= len(market):
        return None
    hi_a = market["high"].astype(float).values
    lo_a = market["low"].astype(float).values
    sh, sl, sh_i, sl_i = causal_swing_levels(hi_a, lo_a, entry_i)
    long = str(row["direction"]).lower() == "long"
    struct = sh if long else sl
    swing_bar = sh_i if long else sl_i
    feat = extract_b1_bar_features(market, entry_i, row["direction"], struct, swing_bar, act_i)
    return {
        "signal_id": row["signal_id"],
        "marker_bar_timestamp": row["marker_bar_timestamp"],
        "direction": row["direction"],
        "signal_type": row["signal_type"],
        "confidence": row["confidence"],
        "phase44_class": row["confidence"],
        "setup_type": row["signal_type"],
        "b1_delay_min": delay,
        "entry_price": row[f"{prefix}_entry_price"],
        "entry_i": entry_i,
        "stop": row["stop"],
        "target": row["target"],
        "final_r": row[f"{prefix}_net_R"],
        "mae": row[f"{prefix}_MAE_R"],
        "mfe": row[f"{prefix}_MFE_R"],
        "wrong_direction": row[f"{prefix}_wrong_direction"],
        **feat,
    }


def build_features_for_slice(ds: pd.DataFrame, market: pd.DataFrame, win: int) -> pd.DataFrame:
    rows = []
    for _, row in ds.iterrows():
        feat = features_from_dataset_row(row, market, win)
        if feat:
            rows.append(feat)
    return pd.DataFrame(rows)


def build_b1_features_from_control(control: pd.DataFrame, market: pd.DataFrame | None = None) -> pd.DataFrame:
    mkt = market if market is not None else load_market_1m()
    rows = []
    for _, rec in control.iterrows():
        if not rec.get("B_filled"):
            continue
        feat = features_from_control_row(rec, mkt)
        if feat:
            rows.append(feat)
    return pd.DataFrame(rows)
