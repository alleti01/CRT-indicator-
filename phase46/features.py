"""Attach VWAP features to B0 trades."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .baseline import apply_b0, build_oos_frame
from .vwap import (
    atr_distance,
    detect_reclaim_window,
    hlc3,
    signed_vwap_distance,
    vwap_at_index,
)


def _bar_index(market: pd.DataFrame, ts: pd.Timestamp) -> int:
    ts = pd.Timestamp(ts).tz_convert(market.index.tz)
    if ts in market.index:
        return int(market.index.get_loc(ts))
    return int(market.index.searchsorted(ts, side="left"))


def enrich_b0_trades(oos: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP diagnostics for all OOS rows; B0 fills get full feature set."""
    rows = []
    for _, row in oos.iterrows():
        rec = row.to_dict()
        rec["b0_filled"] = bool(rec.get("B0_filled", False))
        act = pd.Timestamp(rec["actionable_timestamp"])
        if act.tzinfo is not None:
            act = act.tz_convert(market.index.tz)
        act_i = _bar_index(market, act)
        rec["actionable_i"] = act_i
        if not rec["b0_filled"]:
            rec["vwap_at_confirm"] = np.nan
            rec["above_vwap"] = np.nan
            rec["reclaim_vwap"] = False
            rows.append(rec)
            continue
        entry_time = rec.get("B0_entry_time")
        if pd.isna(entry_time):
            rows.append(rec)
            continue
        entry_i = _bar_index(market, pd.Timestamp(entry_time))
        entry_px = float(rec["B0_entry_price"])
        direction = rec["direction"]
        v_confirm = vwap_at_index(market, entry_i)
        v_act = vwap_at_index(market, act_i)
        atr = float(market.iloc[entry_i].get("atr", np.nan))
        rec["entry_i"] = entry_i
        rec["b1_confirm_time"] = entry_time
        rec["b1_delay_min"] = float(rec.get("B0_delay_min", np.nan))
        rec["vwap_at_confirm"] = v_confirm
        rec["vwap_at_actionable"] = v_act
        rec["vwap_at_entry"] = v_confirm
        rec["signed_vwap_dist"] = signed_vwap_distance(entry_px, v_confirm, direction)
        rec["abs_vwap_dist_atr"] = atr_distance(entry_px, v_confirm, atr)
        rec["above_vwap"] = int(entry_px > v_confirm) if str(direction).lower() == "long" else int(entry_px < v_confirm)
        rec["vwap_slope_1"] = float(market.iloc[entry_i].get("vwap_slope_1", np.nan))
        rec["vwap_slope_3"] = float(market.iloc[entry_i].get("vwap_slope_3", np.nan))
        rec["vwap_slope_5"] = float(market.iloc[entry_i].get("vwap_slope_5", np.nan))
        rec["vwap_slope_10"] = float(market.iloc[entry_i].get("vwap_slope_10", np.nan))
        rec["reclaim_vwap"] = detect_reclaim_window(market, act_i, entry_i, direction)
        rec["atr_1m"] = atr
        rows.append(rec)
    return pd.DataFrame(rows)


def build_trade_features() -> pd.DataFrame:
    market = load_market_1m()
    from .vwap import attach_session_vwap

    market = attach_session_vwap(market)
    oos = apply_b0(build_oos_frame())
    return enrich_b0_trades(oos, market)
