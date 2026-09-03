"""Frozen Phase45 B1 entry population."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.walkforward import _slice, apply_model_b, pick_best_price_rule

from .config import P45_WF, WALK_FORWARD_FOLDS


def _resolve_entry_timestamp(row: pd.Series) -> pd.Timestamp:
    w = int(row.get("selected_window", row.get("B_window", row.get("b1_window", 10))))
    col = f"B1_w{w}_entry_time"
    if col in row.index and pd.notna(row.get(col)):
        return pd.Timestamp(row[col])
    return pd.Timestamp(row["actionable_timestamp"]) + pd.Timedelta(minutes=float(row["B_delay_min"]))


def load_frozen_entries() -> pd.DataFrame:
    """Canonical stitched OOS B1 fills from Phase45 walk-forward."""
    wf = pd.read_csv(P45_WF, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    # Parse B1 entry time columns
    for win in (5, 10, 15):
        c = f"B1_w{win}_entry_time"
        if c in wf.columns:
            wf[c] = pd.to_datetime(wf[c], utc=True).dt.tz_convert("America/Chicago")
    filled = wf.loc[wf["B_filled"]].copy()
    filled["entry_timestamp"] = filled.apply(_resolve_entry_timestamp, axis=1)
    filled["entry_price"] = filled["B_entry_price"]
    filled["entry_delay_min"] = filled["B_delay_min"]
    filled["control_net_R"] = filled["B_net_R"]
    filled["control_MFE_R"] = filled["B_MFE_R"]
    filled["control_MAE_R"] = filled["B_MAE_R"]
    filled["control_exit_type"] = filled["B_exit_type"]
    filled["control_wrong_direction"] = filled["B_wrong_direction"]
    filled["initial_stop"] = filled["stop"]
    filled["initial_target"] = filled["target"]
    filled["b1_window"] = filled["selected_window"]
    return filled.reset_index(drop=True)


def entry_index(market: pd.DataFrame, ts) -> int:
    ts = pd.Timestamp(ts).tz_convert(market.index.tz)
    if ts in market.index:
        return int(market.index.get_loc(ts))
    return int(market.index.searchsorted(ts, side="left"))


def build_train_entries(dataset: pd.DataFrame, market: pd.DataFrame, fold_i: int, tr_s: str, tr_e: str) -> pd.DataFrame:
    """B1 train fills using Phase45 dataset columns (same as walk_forward_price)."""
    train = _slice(dataset, tr_s, tr_e)
    if train.empty:
        return pd.DataFrame()
    rule, win = pick_best_price_rule(train)
    bdf = apply_model_b(train, rule, win)
    filled = bdf.loc[bdf["B_filled"]].copy()
    if filled.empty:
        return pd.DataFrame()
    filled["entry_timestamp"] = filled.apply(_resolve_entry_timestamp, axis=1)
    filled["entry_price"] = filled["B_entry_price"]
    filled["entry_delay_min"] = filled["B_delay_min"]
    filled["b1_window"] = win
    filled["fold"] = fold_i
    filled["initial_stop"] = filled["stop"]
    filled["initial_target"] = filled["target"]
    filled["phase44_entry"] = filled["phase44_entry"]
    return filled.reset_index(drop=True)


def enrich_entry_row(row: pd.Series, market: pd.DataFrame) -> pd.Series:
    r = row.copy()
    ei = entry_index(market, row["entry_timestamp"])
    r["entry_i"] = ei
    if ei < len(market):
        r["atr_entry"] = float(market.iloc[ei].get("atr", np.nan))
    else:
        r["atr_entry"] = np.nan
    r["initial_risk_points"] = abs(float(row["entry_price"]) - float(row["initial_stop"]))
    return r
