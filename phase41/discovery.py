"""Walk-forward causal rule discovery for major reversals."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session

from .config import RTH_SESSION, WALK_FORWARD_FOLDS
from .timing import _simulate_from_bar


RULE_FEATURES_BULL = ("ret_6_atr", "lower_wick_ratio", "close_loc", "reclaim_prior_mid", "micro_higher_low", "dist_ema20_atr")
RULE_FEATURES_BEAR = ("ret_6_atr", "upper_wick_ratio", "close_loc", "reclaim_prior_mid", "micro_lower_high", "dist_ema20_atr")


def _fit_thresholds(train: pd.DataFrame, direction: str) -> Dict[str, float]:
    sub = train.loc[train["is_major_reversal"] == 1] if "is_major_reversal" in train.columns else train
    pos = train.loc[train["is_major_reversal"] == 1]
    neg = train.loc[train["is_major_reversal"] == 0]
    if direction == "Long":
        return {
            "ret_6_atr_max": float(pos["ret_6_atr"].quantile(0.75)) if len(pos) else -0.8,
            "wick_min": float(pos["lower_wick_ratio"].quantile(0.25)) if len(pos) else 0.35,
            "close_loc_min": 0.52,
            "dist_ema20_max": float(pos["dist_ema20_atr"].quantile(0.70)) if len(pos) else 0.5,
        }
    return {
        "ret_6_atr_min": float(pos["ret_6_atr"].quantile(0.25)) if len(pos) else 0.8,
        "wick_min": float(pos["upper_wick_ratio"].quantile(0.25)) if len(pos) else 0.35,
        "close_loc_max": 0.48,
        "dist_ema20_min": float(pos["dist_ema20_atr"].quantile(0.30)) if len(pos) else -0.5,
    }


def bull_trigger(row, thr: dict) -> bool:
    return (
        float(row.get("ret_6_atr", 0)) <= thr["ret_6_atr_max"]
        and float(row.get("lower_wick_ratio", 0)) >= thr["wick_min"]
        and float(row.get("close_loc", 0.5)) >= thr["close_loc_min"]
        and (float(row.get("reclaim_prior_mid", 0)) >= 1 or float(row.get("micro_higher_low", 0)) >= 1)
        and float(row.get("dist_ema20_atr", 0)) <= thr["dist_ema20_max"]
    )


def bear_trigger(row, thr: dict) -> bool:
    return (
        float(row.get("ret_6_atr", 0)) >= thr["ret_6_atr_min"]
        and float(row.get("upper_wick_ratio", 0)) >= thr["wick_min"]
        and float(row.get("close_loc", 0.5)) <= thr["close_loc_max"]
        and (float(row.get("reclaim_prior_mid", 0)) <= 0 or float(row.get("micro_lower_high", 0)) >= 1)
        and float(row.get("dist_ema20_atr", 0)) >= thr["dist_ema20_min"]
    )


def scan_signals(feats: pd.DataFrame, thr_bull: dict, thr_bear: dict) -> pd.DataFrame:
    rows = []
    for ts, row in feats.iterrows():
        if bull_trigger(row, thr_bull):
            rows.append({"marker_bar_timestamp": ts, "signal_type": "MRL", "direction": "Long"})
        elif bear_trigger(row, thr_bear):
            rows.append({"marker_bar_timestamp": ts, "signal_type": "MRS", "direction": "Short"})
    return pd.DataFrame(rows)


def walk_forward_discovery(dataset: pd.DataFrame, market: pd.DataFrame, feats: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Train thresholds on true/false dataset; scan feats for OOS signals."""
    wf_rows = []
    oos_trades = []
    pos = {ts: i for i, ts in enumerate(market.index)}

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, start=1):
        tz = dataset["timestamp"].dt.tz
        train = dataset.loc[(dataset["timestamp"] >= pd.Timestamp(tr_s, tz=tz)) & (dataset["timestamp"] <= pd.Timestamp(tr_e, tz=tz))]
        test_feats = feats.loc[(feats.index >= pd.Timestamp(te_s, tz=tz)) & (feats.index <= pd.Timestamp(te_e, tz=tz))]
        if len(train) < 50:
            continue
        thr_b = _fit_thresholds(train.loc[train["direction"] == "Long"], "Long")
        thr_s = _fit_thresholds(train.loc[train["direction"] == "Short"], "Short")
        sigs = scan_signals(test_feats, thr_b, thr_s)
        fold_preds = []
        for sig in sigs.itertuples(index=False):
            ts = pd.Timestamp(sig.marker_bar_timestamp)
            if ts not in pos:
                continue
            d = 1 if sig.direction == "Long" else -1
            sim = _simulate_from_bar(market, pos[ts], d, stop_atr=0.75, target_r=2.0, max_bars=4)
            if not sim:
                continue
            tr = {
                "fold": fold_i,
                "marker_bar_timestamp": ts,
                "signal_type": sig.signal_type,
                "direction": sig.direction,
                "realized_R": sim["realized_R"],
                "MFE_R": sim["MFE_R"],
                "MAE_R": sim["MAE_R"],
            }
            oos_trades.append(tr)
            fold_preds.append(tr)
        wf_rows.append({"fold": fold_i, "test_N": len(fold_preds), "test_AvgR": np.mean([t["realized_R"] for t in fold_preds]) if fold_preds else np.nan})

    rules = {
        "name": "EXTENSION_REJECTION_RECLAIM",
        "description": "6-bar extension + rejection wick + reclaim/micro-structure + EMA20 stretch (walk-forward thresholds)",
        "bull_conditions": ["ret_6_atr <= train_q75", "lower_wick >= train_q25", "close_loc >= 0.52", "reclaim_or_higher_low", "dist_ema20 <= train_q70"],
        "bear_conditions": ["ret_6_atr >= train_q25", "upper_wick >= train_q25", "close_loc <= 0.48", "lower_high_or_fail_reclaim", "dist_ema20 >= train_q30"],
    }
    return pd.DataFrame(wf_rows), pd.DataFrame(oos_trades), rules
