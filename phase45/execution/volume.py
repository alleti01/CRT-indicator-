"""1m volume confirmation features."""

from __future__ import annotations

import numpy as np
import pandas as pd


def volume_features(market: pd.DataFrame, i: int, direction: str, bos_i: int) -> dict:
    row = market.iloc[i]
    vol = float(row["volume"])
    rel = float(row["rel_volume"]) if np.isfinite(row["rel_volume"]) else np.nan
    ma5 = float(row["vol_ma5"]) if np.isfinite(row["vol_ma5"]) else np.nan
    vol_exp = vol / ma5 if ma5 and ma5 > 0 else np.nan
    d = 1 if str(direction).lower() == "long" else -1
    ret1 = 0.0
    if i >= 1:
        ret1 = (float(row.close) / float(market.iloc[i - 1].close) - 1) * d
    dir_vol = ret1 * rel if np.isfinite(rel) else np.nan
    bos_vol = np.nan
    if bos_i >= 0:
        bvol = float(market.iloc[bos_i]["volume"])
        past = market["volume"].astype(float).iloc[max(0, bos_i - 20) : bos_i].mean()
        bos_vol = bvol / past if past > 0 else np.nan
    pull_ratio = np.nan
    if bos_i >= 0 and bos_i < i:
        impulse = market["volume"].astype(float).iloc[max(0, bos_i - 3) : bos_i + 1].mean()
        pull = market["volume"].astype(float).iloc[bos_i + 1 : i + 1].mean()
        pull_ratio = pull / impulse if impulse > 0 else np.nan
    return {
        "rel_volume_1m": rel,
        "volume_expansion": vol_exp,
        "directional_volume_response": dir_vol,
        "breakout_volume": bos_vol,
        "pullback_volume_ratio": pull_ratio,
    }


def volume_pass(feat: dict, direction: str, rel_thr: float) -> bool:
    d = 1 if str(direction).lower() == "long" else -1
    rel = feat.get("rel_volume_1m", np.nan)
    dvr = feat.get("directional_volume_response", np.nan)
    pvr = feat.get("pullback_volume_ratio", np.nan)
    if not np.isfinite(rel) or rel < rel_thr:
        return False
    if np.isfinite(dvr) and dvr <= 0:
        return False
    if np.isfinite(pvr) and pvr > 1.2:
        return False
    return True
