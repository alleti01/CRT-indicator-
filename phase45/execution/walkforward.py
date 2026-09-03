"""Walk-forward selection for 1m price/volume rules."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import performance

from .config import EXEC_WINDOWS_MIN, PRICE_RULES, VOL_THRESHOLDS, WALK_FORWARD_FOLDS
from .volume import volume_pass


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["marker_bar_timestamp"])
    tz = ts.dt.tz
    lo = pd.Timestamp(start, tz=tz)
    hi = pd.Timestamp(end, tz=tz)
    return df.loc[(ts >= lo) & (ts <= hi)].copy()


def pick_best_price_rule(train: pd.DataFrame, *, min_fill_rate: float = 0.5, min_fills: int = 30) -> tuple[str, int]:
    best = ("B1", 10)
    best_avgr = -999.0
    fallback = ("B1", 10)
    fallback_score = -999.0
    n_train = len(train)
    for rule in PRICE_RULES:
        for win in EXEC_WINDOWS_MIN:
            fill = f"{rule}_w{win}_filled"
            col = f"{rule}_w{win}_net_R"
            if fill not in train.columns or col not in train.columns:
                continue
            sub = train.loc[train[fill]]
            if len(sub) < min_fills:
                continue
            fr = len(sub) / n_train if n_train else 0.0
            avgr = float(sub[col].mean())
            if fr >= min_fill_rate and avgr > best_avgr:
                best_avgr = avgr
                best = (rule, win)
            if avgr > fallback_score:
                fallback_score = avgr
                fallback = (rule, win)
    return best if best_avgr > -999.0 else fallback


def apply_model_b(df: pd.DataFrame, rule: str, win: int) -> pd.DataFrame:
    prefix = f"{rule}_w{win}"
    out = df.copy()
    out["B_filled"] = out[f"{prefix}_filled"]
    out["B_net_R"] = out.get(f"{prefix}_net_R", np.nan)
    out["B_gross_R"] = out.get(f"{prefix}_gross_R", np.nan)
    out["B_MFE_R"] = out.get(f"{prefix}_MFE_R", np.nan)
    out["B_MAE_R"] = out.get(f"{prefix}_MAE_R", np.nan)
    out["B_delay_min"] = out.get(f"{prefix}_delay_min", np.nan)
    out["B_entry_price"] = out.get(f"{prefix}_entry_price", np.nan)
    out["B_wrong_direction"] = out.get(f"{prefix}_wrong_direction", np.nan)
    out["B_exit_type"] = out.get(f"{prefix}_exit_type", np.nan)
    out["B_rule"] = rule
    out["B_window"] = win
    return out


def walk_forward_price(dataset: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts: list[pd.DataFrame] = []
    selections: list[dict] = []
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train = _slice(dataset, tr_s, tr_e)
        test = _slice(dataset, te_s, te_e)
        if train.empty or test.empty:
            continue
        rule, win = pick_best_price_rule(train)
        bdf = apply_model_b(test, rule, win)
        bdf["fold"] = fold_i
        bdf["train_start"] = tr_s
        bdf["train_end"] = tr_e
        bdf["test_start"] = te_s
        bdf["test_end"] = te_e
        bdf["selected_rule"] = rule
        bdf["selected_window"] = win
        parts.append(bdf)
        selections.append(
            {
                "fold": fold_i,
                "train_start": tr_s,
                "train_end": tr_e,
                "test_start": te_s,
                "test_end": te_e,
                "selected_rule": rule,
                "selected_window": win,
                "train_N": len(train),
                "test_N": len(test),
            }
        )
    stitched = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return stitched, pd.DataFrame(selections)


def walk_forward_volume(dataset: pd.DataFrame, stitched: pd.DataFrame, param_stab: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply train-selected volume threshold per fold to stitched TEST fills."""
    parts: list[pd.DataFrame] = []
    params: list[dict] = []
    if stitched.empty or param_stab.empty:
        return pd.DataFrame(), pd.DataFrame()
    for _, fold in param_stab.iterrows():
        fold_i = int(fold["fold"])
        rule = str(fold["selected_rule"])
        win = int(fold["selected_window"])
        prefix = f"{rule}_w{win}"
        rel_col = f"{prefix}_rel_volume_1m"
        train = _slice(dataset, fold["train_start"], fold["train_end"])
        test = stitched.loc[stitched["fold"] == fold_i].copy()
        if test.empty:
            continue
        filled_train = train.loc[train[f"{prefix}_filled"]] if f"{prefix}_filled" in train.columns else pd.DataFrame()
        best_thr = VOL_THRESHOLDS[0]
        best_avgr = -999.0
        for thr in VOL_THRESHOLDS:
            if rel_col not in filled_train.columns:
                continue
            sub = filled_train.loc[filled_train[rel_col] >= thr]
            if len(sub) < 15:
                continue
            avgr = float(sub[f"{prefix}_net_R"].mean())
            if avgr > best_avgr:
                best_avgr = avgr
                best_thr = thr
        te = test.copy()
        te["C_filled"] = False
        te["C_net_R"] = np.nan
        te["C_gross_R"] = np.nan
        te["C_MAE_R"] = np.nan
        te["C_MFE_R"] = np.nan
        te["C_wrong_direction"] = np.nan
        te["volume_threshold"] = best_thr
        for idx, row in te.iterrows():
            if not row["B_filled"]:
                continue
            feat = {
                "rel_volume_1m": row.get(rel_col, np.nan),
                "directional_volume_response": row.get(f"{prefix}_directional_volume_response", np.nan),
                "pullback_volume_ratio": row.get(f"{prefix}_pullback_volume_ratio", np.nan),
            }
            if volume_pass(feat, row["direction"], best_thr):
                te.at[idx, "C_filled"] = True
                te.at[idx, "C_net_R"] = row["B_net_R"]
                te.at[idx, "C_gross_R"] = row["B_gross_R"]
                te.at[idx, "C_MAE_R"] = row["B_MAE_R"]
                te.at[idx, "C_MFE_R"] = row["B_MFE_R"]
                te.at[idx, "C_wrong_direction"] = row["B_wrong_direction"]
        parts.append(te)
        params.append(
            {
                "fold": fold_i,
                "volume_threshold": best_thr,
                "train_filled_N": int(len(filled_train)),
                "selected_rule": rule,
                "selected_window": win,
            }
        )
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return out, pd.DataFrame(params)


def walk_forward_summary(stitched: pd.DataFrame, *, col: str = "B_net_R", filled_col: str = "B_filled") -> dict:
    sub = stitched.loc[stitched[filled_col]] if not stitched.empty else stitched
    return performance(sub, col=col) if not sub.empty else {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0}
