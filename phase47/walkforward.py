"""Walk-forward nested parameter selection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m
from phase45.execution.walkforward import _slice, pick_best_price_rule

from .config import (
    BODY_ATR_MIN,
    BODY_RANGE_MIN,
    BREAK_STRENGTH_MIN_ATR,
    CLOSE_QUALITY_MIN,
    OPPOSING_WICK_MAX,
    P45_DATASET,
    RANGE_ATR_MIN,
    RETEST_TOL_ATR,
    STRUCTURE_AGE_MIN,
    STRUCTURE_TOUCHES_MIN,
    WALK_FORWARD_FOLDS,
)
from .features import build_features_for_slice
from .structure import causal_swing_levels
from .variants import (
    follow_through_entry,
    pass_body_atr,
    pass_body_range,
    pass_break_strength,
    pass_close_quality,
    pass_liquidity_sweep,
    pass_opposing_wick,
    pass_range_atr,
    pass_structure_age,
    pass_structure_touches,
    retest_entry,
    simulate_variant_entry,
)


def _select_param(train: pd.DataFrame, fn, grid: tuple, *, min_n: int = 20) -> float:
    best, best_avgr = grid[0], -999.0
    for p in grid:
        mask = train.apply(lambda r: fn(r, p), axis=1)
        sub = train.loc[mask]
        if len(sub) < min_n:
            continue
        avgr = float(sub["final_r"].mean())
        if avgr > best_avgr:
            best_avgr, best = avgr, p
    return best


FILTER_VARIANTS = {
    "Break_Strength": (pass_break_strength, BREAK_STRENGTH_MIN_ATR),
    "Displacement_BodyRange": (pass_body_range, BODY_RANGE_MIN),
    "Displacement_RangeATR": (pass_range_atr, RANGE_ATR_MIN),
    "Displacement_BodyATR": (pass_body_atr, BODY_ATR_MIN),
    "Close_Quality": (pass_close_quality, CLOSE_QUALITY_MIN),
    "Wick_Quality": (pass_opposing_wick, OPPOSING_WICK_MAX),
    "Structure_Touches": (pass_structure_touches, STRUCTURE_TOUCHES_MIN),
    "Structure_Age": (pass_structure_age, STRUCTURE_AGE_MIN),
}


def walk_forward_filters(market: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    mkt = market if market is not None else load_market_1m()
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    parts, params = [], []
    for vname, (fn, grid) in FILTER_VARIANTS.items():
        for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
            train_ds = _slice(ds, tr_s, tr_e)
            test_ds = _slice(ds, te_s, te_e)
            if train_ds.empty or test_ds.empty:
                continue
            rule, win = pick_best_price_rule(train_ds)
            train_f = build_features_for_slice(train_ds, mkt, win)
            test_f = build_features_for_slice(test_ds, mkt, win)
            if train_f.empty or test_f.empty:
                continue
            param = _select_param(train_f, fn, grid)
            te = test_f.copy()
            te["V_pass"] = te.apply(lambda r: fn(r, param), axis=1)
            te["V_net_R"] = np.where(te["V_pass"], te["final_r"], np.nan)
            te["V_MAE_R"] = np.where(te["V_pass"], te["mae"], np.nan)
            te["V_MFE_R"] = np.where(te["V_pass"], te["mfe"], np.nan)
            te["V_wrong_direction"] = np.where(te["V_pass"], te["wrong_direction"], np.nan)
            te["V_delay_min"] = te["b1_delay_min"]
            te["variant"] = vname
            te["fold"] = fold_i
            te["b1_window"] = win
            parts.append(te)
            params.append({"fold": fold_i, "variant": vname, "b1_window": win, "parameter": param, "train_N": len(train_f)})
    # Liquidity (boolean)
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train_ds = _slice(ds, tr_s, tr_e)
        test_ds = _slice(ds, te_s, te_e)
        rule, win = pick_best_price_rule(train_ds)
        test_f = build_features_for_slice(test_ds, mkt, win)
        if test_f.empty:
            continue
        te = test_f.copy()
        te["V_pass"] = te.apply(pass_liquidity_sweep, axis=1)
        te["V_net_R"] = np.where(te["V_pass"], te["final_r"], np.nan)
        te["V_MAE_R"] = np.where(te["V_pass"], te["mae"], np.nan)
        te["V_MFE_R"] = np.where(te["V_pass"], te["mfe"], np.nan)
        te["V_wrong_direction"] = np.where(te["V_pass"], te["wrong_direction"], np.nan)
        te["V_delay_min"] = te["b1_delay_min"]
        te["variant"] = "Local_Liquidity"
        te["fold"] = fold_i
        parts.append(te)
        params.append({"fold": fold_i, "variant": "Local_Liquidity", "parameter": "sweep_required", "train_N": len(build_features_for_slice(train_ds, mkt, win))})
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(), pd.DataFrame(params)


def walk_forward_delayed(control: pd.DataFrame, market: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Follow-through (F1-F4) or Retest variants with delayed entry simulation."""
    parts, params = [], []
    fvars = ("F1", "F2", "F3", "F4") if mode == "follow" else ("Retest",)
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        test = control.loc[control["fold"] == fold_i].copy()
        test = test.loc[test["B_filled"]]
        if test.empty:
            continue
        best_tol = RETEST_TOL_ATR[0]
        if mode == "retest":
            train_ds = _slice(pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp"]), tr_s, tr_e)
            _, win = pick_best_price_rule(train_ds)
            filled = train_ds.loc[train_ds[f"B1_w{win}_filled"]] if f"B1_w{win}_filled" in train_ds.columns else pd.DataFrame()
            best_avgr = -999.0
            for tol in RETEST_TOL_ATR:
                if len(filled) >= 10:
                    avgr = float(filled[f"B1_w{win}_net_R"].mean())
                    if avgr > best_avgr:
                        best_avgr, best_tol = avgr, tol
        for fvar in fvars:
            rows = []
            for _, rec in test.iterrows():
                act = pd.Timestamp(rec["actionable_timestamp"]).tz_convert(market.index.tz)
                delay = float(rec["B_delay_min"])
                bos_i = int(market.index.searchsorted(act + pd.Timedelta(minutes=delay), side="left"))
                if bos_i >= len(market):
                    continue
                sh, sl, _, _ = causal_swing_levels(market["high"].astype(float).values, market["low"].astype(float).values, bos_i)
                struct = sh if str(rec["direction"]).lower() == "long" else sl
                if mode == "follow":
                    ok, ei, px = follow_through_entry(market, bos_i, rec["direction"], fvar, struct, rec["stop"], rec["target"], rec["signal_type"])
                    vlabel = f"Follow_{fvar}"
                else:
                    ok, ei, px = retest_entry(market, bos_i, rec["direction"], struct, best_tol, rec["stop"], rec["target"], rec["signal_type"])
                    vlabel = "Retest"
                base = rec.to_dict()
                if ok:
                    sim = simulate_variant_entry(market, ei, px, rec["stop"], rec["target"], rec["direction"], rec["signal_type"])
                    base.update({"V_pass": True, "V_net_R": sim["net_R"], "V_MAE_R": sim["MAE_R"], "V_MFE_R": sim["MFE_R"], "V_wrong_direction": sim["wrong_direction"], "V_delay_min": delay + (ei - bos_i), "variant": vlabel, "final_r": sim["net_R"], "mae": sim["MAE_R"], "mfe": sim["MFE_R"], "wrong_direction": sim["wrong_direction"], "b1_delay_min": delay + (ei - bos_i)})
                else:
                    base.update({"V_pass": False, "V_net_R": np.nan, "variant": vlabel})
                rows.append(base)
            if rows:
                df = pd.DataFrame(rows)
                df["fold"] = fold_i
                parts.append(df)
                params.append({"fold": fold_i, "variant": fvars[0] if mode == "retest" else fvar, "parameter": best_tol if mode == "retest" else fvar})
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(), pd.DataFrame(params)
