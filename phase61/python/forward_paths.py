"""Phase61 — forward path metrics for raw causal signals."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = [1, 2, 3, 5, 10, 15, 30, 60]
ATR_THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
ADV_THRESHOLDS = [-0.5, -1.0]


def _entry_indices(signals: pd.DataFrame) -> np.ndarray:
    return signals["entry_i"].values.astype(int)


def compute_forward_paths(
    m1_hi: np.ndarray,
    m1_lo: np.ndarray,
    m1_cl: np.ndarray,
    m1_op: np.ndarray,
    signal_i: np.ndarray,
    direction: np.ndarray,
    atr: np.ndarray,
    max_h: int = 60,
) -> pd.DataFrame:
    """Vectorized forward paths from entry bar (signal_i+1) for each signal."""
    n = len(signal_i)
    entry_i = np.minimum(signal_i + 1, len(m1_cl) - max_h - 1)
    ep = m1_op[entry_i]
    a = np.where(np.isfinite(atr) & (atr > 0), atr, 1.0)
    d_sign = np.where(direction == "LONG", 1.0, -1.0)

    out = {
        "signal_i": signal_i,
        "entry_i": entry_i,
        "entry_price": ep,
        "direction": direction,
        "atr": a,
    }

    for h in HORIZONS:
        idx = entry_i + h - 1
        idx = np.clip(idx, 0, len(m1_cl) - 1)
        ret = (m1_cl[idx] - ep) * d_sign
        out[f"ret_{h}m"] = ret
        out[f"ret_{h}m_atr"] = ret / a
        out[f"dir_ok_{h}m"] = ret > 0

    # Rolling MFE/MAE over 60 bars from entry
    mfe = np.zeros(n)
    mae = np.zeros(n)
    mfe_bar = np.full(n, max_h, dtype=int)
    mae_bar = np.full(n, max_h, dtype=int)
    mfe_before_mae = np.zeros(n, dtype=bool)
    final_ret_60 = np.zeros(n)

    for k in range(n):
        j = entry_i[k]
        end = min(j + max_h, len(m1_cl))
        hs = m1_hi[j:end]
        ls = m1_lo[j:end]
        if direction[k] == "LONG":
            fav = (np.maximum.accumulate(hs) - ep[k]) / a[k]
            adv = (ep[k] - np.minimum.accumulate(ls)) / a[k]
            final_ret_60[k] = (m1_cl[end - 1] - ep[k]) / a[k]
        else:
            fav = (ep[k] - np.minimum.accumulate(ls)) / a[k]
            adv = (np.maximum.accumulate(hs) - ep[k]) / a[k]
            final_ret_60[k] = (ep[k] - m1_cl[end - 1]) / a[k]
        mfe[k] = float(np.max(fav)) if len(fav) else 0.0
        mae[k] = float(np.max(adv)) if len(adv) else 0.0
        if len(fav):
            mfe_bar[k] = int(np.argmax(fav)) + 1
            mae_bar[k] = int(np.argmax(adv)) + 1
            mfe_before_mae[k] = mfe_bar[k] <= mae_bar[k]

    out["mfe_60m_atr"] = mfe
    out["mae_60m_atr"] = mae
    out["mfe_before_mae"] = mfe_before_mae
    out["final_ret_60m_atr"] = final_ret_60

    for h in [15, 30, 60]:
        sub_mfe = []
        sub_mae = []
        for k in range(n):
            j = entry_i[k]
            end = min(j + h, len(m1_cl))
            hs = m1_hi[j:end]
            ls = m1_lo[j:end]
            if direction[k] == "LONG":
                sub_mfe.append((np.max(hs) - ep[k]) / a[k] if len(hs) else 0)
                sub_mae.append((ep[k] - np.min(ls)) / a[k] if len(ls) else 0)
            else:
                sub_mfe.append((ep[k] - np.min(ls)) / a[k] if len(ls) else 0)
                sub_mae.append((np.max(hs) - ep[k]) / a[k] if len(ls) else 0)
        out[f"mfe_{h}m_atr"] = sub_mfe
        out[f"mae_{h}m_atr"] = sub_mae

    # Time to ATR thresholds
    for thr in ATR_THRESHOLDS + [x for x in ATR_THRESHOLDS]:
        pass

    for thr in ATR_THRESHOLDS:
        t_fav = np.full(n, np.nan)
        mae_before = np.full(n, np.nan)
        for k in range(n):
            j = entry_i[k]
            end = min(j + max_h, len(m1_cl))
            hs = m1_hi[j:end]
            ls = m1_lo[j:end]
            if direction[k] == "LONG":
                fav_path = (hs - ep[k]) / a[k]
                adv_path = (ep[k] - ls) / a[k]
            else:
                fav_path = (ep[k] - ls) / a[k]
                adv_path = (hs - ep[k]) / a[k]
            hit = np.where(fav_path >= thr)[0]
            if len(hit):
                t_fav[k] = hit[0] + 1
                mae_before[k] = float(np.max(adv_path[: hit[0] + 1])) if hit[0] >= 0 else 0.0
        out[f"time_to_plus_{thr}atr"] = t_fav
        out[f"mae_before_plus_{thr}atr"] = mae_before
        out[f"reached_plus_{thr}atr"] = np.isfinite(t_fav)

    for thr in ADV_THRESHOLDS:
        t_adv = np.full(n, np.nan)
        for k in range(n):
            j = entry_i[k]
            end = min(j + max_h, len(m1_cl))
            hs = m1_hi[j:end]
            ls = m1_lo[j:end]
            if direction[k] == "LONG":
                adv_path = (ep[k] - ls) / a[k]
            else:
                adv_path = (hs - ep[k]) / a[k]
            hit = np.where(adv_path >= abs(thr))[0]
            if len(hit):
                t_adv[k] = hit[0] + 1
        out[f"time_to_{thr}atr"] = t_adv

    return pd.DataFrame(out)


def horizon_summary(paths: pd.DataFrame, direction: str | None = None) -> dict:
    sub = paths if direction is None else paths[paths["direction"] == direction]
    r = {}
    for h in HORIZONS:
        col = f"dir_ok_{h}m"
        if col in sub.columns:
            r[f"{h}m"] = float(sub[col].mean()) if len(sub) else 0.0
    for h in [15, 30, 60]:
        r[f"median_mfe_{h}m"] = float(sub[f"mfe_{h}m_atr"].median()) if len(sub) else 0.0
        r[f"median_mae_{h}m"] = float(sub[f"mae_{h}m_atr"].median()) if len(sub) else 0.0
    for thr in [1.0, 2.0, 2.5, 3.0]:
        col = f"reached_plus_{thr}atr"
        if col in sub.columns:
            r[f"plus_{thr}atr"] = float(sub[col].mean()) if len(sub) else 0.0
    return r
