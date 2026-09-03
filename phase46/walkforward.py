"""Walk-forward parameter selection for VWAP variants."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import performance

from .config import V3_SLOPE_WINDOWS, V4_MAX_DIST_ATR, V5_TOL_ATR, V5_WAIT_BARS, WALK_FORWARD_FOLDS
from .variants import apply_variant_mask


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["marker_bar_timestamp"])
    tz = ts.dt.tz
    lo = pd.Timestamp(start, tz=tz)
    hi = pd.Timestamp(end, tz=tz)
    return df.loc[(ts >= lo) & (ts <= hi)].copy()


def _train_select_v3(train: pd.DataFrame) -> str:
    best_col = "vwap_slope_3"
    best_avgr = -999.0
    b0 = train.loc[train["b0_filled"]]
    for n in V3_SLOPE_WINDOWS:
        col = f"vwap_slope_{n}"
        if col not in train.columns:
            continue
        mask = b0.apply(lambda r: (r[col] > 0 if str(r["direction"]).lower() == "long" else r[col] < 0), axis=1)
        sub = b0.loc[mask.index[mask]]
        if len(sub) < 20:
            continue
        avgr = float(sub["B0_net_R"].mean())
        if avgr > best_avgr:
            best_avgr = avgr
            best_col = col
    return best_col


def _train_select_v4(train: pd.DataFrame) -> float | None:
    best_thr = V4_MAX_DIST_ATR[-1]
    best_avgr = -999.0
    b0 = train.loc[train["b0_filled"]]
    for thr in V4_MAX_DIST_ATR:
        sub = b0.loc[b0["abs_vwap_dist_atr"] <= thr]
        if len(sub) < 20:
            continue
        avgr = float(sub["B0_net_R"].mean())
        if avgr > best_avgr:
            best_avgr = avgr
            best_thr = thr
    return best_thr


def walk_forward_variant(
    trades: pd.DataFrame,
    variant: str,
    *,
    v5_frame: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stitched OOS TEST for parameterized VWAP variants."""
    parts: list[pd.DataFrame] = []
    params: list[dict] = []
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train = _slice(trades, tr_s, tr_e)
        test = _slice(trades, te_s, te_e)
        if train.empty or test.empty:
            continue
        te = test.copy()
        te["fold"] = fold_i
        param_rec: dict = {"fold": fold_i, "variant": variant, "train_start": tr_s, "train_end": tr_e, "test_start": te_s, "test_end": te_e}

        if variant == "V1":
            te["V_pass"] = te.apply(lambda r: r["b0_filled"] and (
                (r["B0_entry_price"] > r["vwap_at_confirm"] if str(r["direction"]).lower() == "long" else r["B0_entry_price"] < r["vwap_at_confirm"])
            ), axis=1)
            param_rec["parameter"] = "side_alignment"
        elif variant == "V2":
            te["V_pass"] = te["b0_filled"] & te["reclaim_vwap"]
            param_rec["parameter"] = "reclaim_loss"
        elif variant == "V3":
            slope_col = _train_select_v3(train)
            te["V_pass"] = te.apply(lambda r: r["b0_filled"] and (
                (r.get(slope_col, 0) > 0 if str(r["direction"]).lower() == "long" else r.get(slope_col, 0) < 0)
            ), axis=1)
            param_rec["parameter"] = slope_col
        elif variant == "V4":
            thr = _train_select_v4(train)
            te["V_pass"] = te["b0_filled"] & (te["abs_vwap_dist_atr"] <= thr)
            param_rec["parameter"] = thr
        elif variant == "V5" and v5_frame is not None:
            v5_test = _slice(v5_frame, te_s, te_e)
            # pick best tol/wait on train from v5 columns
            best_key = None
            best_avgr = -999.0
            tr_v5 = _slice(v5_frame, tr_s, tr_e)
            for tol in V5_TOL_ATR:
                for wait in V5_WAIT_BARS:
                    col = f"V5_t{tol}_w{wait}_filled"
                    ncol = f"V5_t{tol}_w{wait}_net_R"
                    if col not in tr_v5.columns:
                        continue
                    sub = tr_v5.loc[tr_v5[col]]
                    if len(sub) < 15:
                        continue
                    avgr = float(sub[ncol].mean())
                    if avgr > best_avgr:
                        best_avgr = avgr
                        best_key = (tol, wait)
            if best_key is None:
                best_key = (V5_TOL_ATR[0], V5_WAIT_BARS[0])
            tol, wait = best_key
            pfx = f"V5_t{tol}_w{wait}"
            te = te.merge(
                v5_test[["signal_id", f"{pfx}_filled", f"{pfx}_net_R", f"{pfx}_MFE_R", f"{pfx}_MAE_R", f"{pfx}_delay_min", f"{pfx}_wrong_direction", f"{pfx}_entry_price"]],
                on="signal_id",
                how="left",
                suffixes=("", "_v5"),
            )
            te["V_pass"] = te[f"{pfx}_filled"].fillna(False).astype(bool)
            te["V_net_R"] = te[f"{pfx}_net_R"]
            te["V_MFE_R"] = te[f"{pfx}_MFE_R"]
            te["V_MAE_R"] = te[f"{pfx}_MAE_R"]
            te["V_delay_min"] = te[f"{pfx}_delay_min"]
            te["V_wrong_direction"] = te[f"{pfx}_wrong_direction"]
            te["V_entry_price"] = te[f"{pfx}_entry_price"]
            param_rec["parameter"] = f"tol={tol},wait={wait}"
        else:
            continue

        if variant != "V5":
            te["V_net_R"] = np.where(te["V_pass"], te["B0_net_R"], np.nan)
            te["V_MFE_R"] = np.where(te["V_pass"], te["B0_MFE_R"], np.nan)
            te["V_MAE_R"] = np.where(te["V_pass"], te["B0_MAE_R"], np.nan)
            te["V_delay_min"] = np.where(te["V_pass"], te["B0_delay_min"], np.nan)
            te["V_wrong_direction"] = np.where(te["V_pass"], te["B0_wrong_direction"], np.nan)
            te["V_entry_price"] = np.where(te["V_pass"], te["B0_entry_price"], np.nan)

        te["V_filled"] = te["V_pass"]
        parts.append(te)
        params.append(param_rec)

    stitched = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return stitched, pd.DataFrame(params)
