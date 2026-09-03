"""Phase57-specific features for location/reaction quality scoring.

All features must be available at decision time (causal).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.data import htf_bar_index


def attach_sequence_features(
    events: pd.DataFrame,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
) -> pd.DataFrame:
    """Attach location, reaction, and context features to sequence events."""
    if events.empty:
        return events
    ev = events.copy()
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    n = len(m1)

    # HTF indices
    m5_i = htf_bar_index(m1.index, m5.index)
    m15_i = htf_bar_index(m1.index, m15.index)
    m5_cl = m5["close"].values.astype(float)
    m15_cl = m15["close"].values.astype(float)
    m5_atr = m5["atr"].values.astype(float) if "atr" in m5.columns else np.full(len(m5), np.nan)
    m15_atr = m15["atr"].values.astype(float) if "atr" in m15.columns else np.full(len(m15), np.nan)

    feats: dict[str, list] = {
        "body_atr": [],
        "range_atr": [],
        "close_loc": [],
        "mom_3": [],
        "atr_ratio": [],
        "m5_mom_3": [],
        "m15_mom_4": [],
        "distance_from_swing_atr": [],
    }

    for _, row in ev.iterrows():
        i = int(row.get("setup_i") or row.get("entry_i") or row.get("bar_i", 0))
        if i < 20 or i >= n:
            for k in feats:
                feats[k].append(np.nan)
            continue

        a = atr[i] if np.isfinite(atr[i]) else 1.0
        feats["body_atr"].append(abs(cl[i] - op[i]) / a)
        feats["range_atr"].append((hi[i] - lo[i]) / a)
        bar_range = hi[i] - lo[i]
        feats["close_loc"].append((cl[i] - lo[i]) / bar_range if bar_range > 0 else 0.5)
        feats["mom_3"].append((cl[i] - cl[i - 3]) / a if i >= 3 else np.nan)

        atr_mean = np.nanmean(atr[max(0, i - 100):i]) if i >= 100 else np.nanmean(atr[:i + 1])
        feats["atr_ratio"].append(a / atr_mean if atr_mean > 0 else np.nan)

        j5 = m5_i[i]
        if j5 >= 3:
            m5a = m5_atr[j5] if np.isfinite(m5_atr[j5]) else 1.0
            feats["m5_mom_3"].append((m5_cl[j5] - m5_cl[j5 - 3]) / m5a)
        else:
            feats["m5_mom_3"].append(np.nan)

        j15 = m15_i[i]
        if j15 >= 4:
            m15a = m15_atr[j15] if np.isfinite(m15_atr[j15]) else 1.0
            feats["m15_mom_4"].append((m15_cl[j15] - m15_cl[j15 - 4]) / m15a)
        else:
            feats["m15_mom_4"].append(np.nan)

        from phase52.research.swings import precompute_swing_highs, precompute_swing_lows
        sh = precompute_swing_highs(hi, 5)
        sl = precompute_swing_lows(lo, 5)
        d_sh = abs(cl[i] - sh[i]) / a if np.isfinite(sh[i]) else np.nan
        d_sl = abs(cl[i] - sl[i]) / a if np.isfinite(sl[i]) else np.nan
        feats["distance_from_swing_atr"].append(min(d_sh, d_sl) if np.isfinite(d_sh) and np.isfinite(d_sl) else np.nan)

    for k, v in feats.items():
        ev[k] = v
    return ev
