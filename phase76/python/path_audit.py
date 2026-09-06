"""Post-entry path audit — MFE/MAE and first-passage probabilities."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (3, 5, 10, 15, 30, 60)
FP_PAIRS = (
    (0.5, 0.5),
    (1.0, 1.0),
    (1.5, 1.0),
    (2.0, 1.0),
    (2.5, 1.0),
    (3.0, 1.0),
    (1.0, 1.5),
    (2.0, 1.5),
    (2.5, 1.5),
)


def path_audit(signals: pd.DataFrame, ohlc: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals
    out = signals.copy()
    idx = ohlc.index
    for h in HORIZONS:
        out[f"mfe_{h}m"] = np.nan
        out[f"mae_{h}m"] = np.nan
    for tg, st in FP_PAIRS:
        out[f"fp_{tg}atr_before_{st}atr"] = np.nan

    for i, row in out.iterrows():
        if pd.isna(row.get("entry_ts")):
            continue
        try:
            start = idx.get_loc(row["entry_ts"])
        except KeyError:
            continue
        entry = row["entry_price"]
        atr = row.get("atr") or ohlc.iloc[start - 1]["atr"] if start > 0 else np.nan
        if pd.isna(atr) or atr <= 0:
            continue
        direction = row["direction"]
        sign = 1 if direction == "LONG" else -1
        end = min(start + 60, len(ohlc) - 1)
        window = ohlc.iloc[start : end + 1]
        if window.empty:
            continue
        highs = window["high"].values
        lows = window["low"].values
        for h in HORIZONS:
            w = window.iloc[: min(h, len(window))]
            if w.empty:
                continue
            if direction == "LONG":
                mfe = (w["high"].max() - entry) / atr
                mae = (entry - w["low"].min()) / atr
            else:
                mfe = (entry - w["low"].min()) / atr
                mae = (w["high"].max() - entry) / atr
            out.at[i, f"mfe_{h}m"] = mfe
            out.at[i, f"mae_{h}m"] = mae

        for tg, st in FP_PAIRS:
            hit_tg = hit_st = False
            for j in range(start, end + 1):
                hi, lo = ohlc.iloc[j]["high"], ohlc.iloc[j]["low"]
                if direction == "LONG":
                    if (hi - entry) / atr >= tg:
                        hit_tg = True
                    if (entry - lo) / atr >= st:
                        hit_st = True
                else:
                    if (entry - lo) / atr >= tg:
                        hit_tg = True
                    if (hi - entry) / atr >= st:
                        hit_st = True
                if hit_tg and not hit_st:
                    out.at[i, f"fp_{tg}atr_before_{st}atr"] = 1.0
                    break
                if hit_st and not hit_tg:
                    out.at[i, f"fp_{tg}atr_before_{st}atr"] = 0.0
                    break
            else:
                if hit_tg and hit_st:
                    out.at[i, f"fp_{tg}atr_before_{st}atr"] = 0.5
    return out


def path_summary(pathed: pd.DataFrame) -> dict:
    if pathed.empty:
        return {"n": 0}
    s = {"n": len(pathed), "family": pathed["family"].iloc[0] if "family" in pathed else ""}
    for h in HORIZONS:
        mfe = pathed[f"mfe_{h}m"].dropna()
        mae = pathed[f"mae_{h}m"].dropna()
        if len(mfe):
            s[f"mfe_{h}m_mean"] = float(mfe.mean())
            s[f"mae_{h}m_mean"] = float(mae.mean())
            s[f"asym_{h}m"] = float(mfe.mean() / mae.mean()) if mae.mean() else np.nan
    return s
