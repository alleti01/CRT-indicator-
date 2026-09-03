"""False reversal control population."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session

from .config import FALSE_CONTROL_PER_TRUE, PRIMARY_OPPORTUNITY, RTH_SESSION


def build_false_controls(market: pd.DataFrame, opportunities: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Bars that look reversal-like but are NOT major opportunities."""
    rth_mask = pd.Series([is_in_session(ts, RTH_SESSION) for ts in market.index], index=market.index)
    m = market.loc[rth_mask]
    opp_ts = set(pd.to_datetime(opportunities["extreme_timestamp"], utc=True))

    # Pseudo-reversal candidates: rejection wick + extension
    atr = m["atr"].astype(float)
    ret6 = (m["close"] - m["close"].shift(6)) / atr
    rng = m["high"] - m["low"]
    upper_wick = (m["high"] - m[["open", "close"]].max(axis=1)) / rng.replace(0, np.nan)
    lower_wick = (m[["open", "close"]].min(axis=1) - m["low"]) / rng.replace(0, np.nan)

    bull_fake = (ret6 < -0.8) & (lower_wick > 0.35) & (~m.index.isin(opp_ts))
    bear_fake = (ret6 > 0.8) & (upper_wick > 0.35) & (~m.index.isin(opp_ts))

    rows = []
    rng_seed = np.random.default_rng(42)
    for mask, direction in ((bull_fake, "Long"), (bear_fake, "Short")):
        idxs = m.index[mask]
        if len(idxs) == 0:
            continue
        n_sample = min(len(idxs), max(len(opportunities) * FALSE_CONTROL_PER_TRUE, 500))
        pick = rng_seed.choice(len(idxs), size=min(n_sample, len(idxs)), replace=False)
        for pi in pick:
            ts = idxs[pi]
            rows.append({"timestamp": ts, "direction": direction, "label": "FALSE_CONTROL", "is_major_reversal": 0})
    return pd.DataFrame(rows)


def build_true_false_dataset(opportunities: pd.DataFrame, false_ctrl: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    true_rows = []
    for opp in opportunities.itertuples(index=False):
        ts = pd.Timestamp(opp.extreme_timestamp)
        row = {"timestamp": ts, "direction": opp.direction, "label": "TRUE_MAJOR", "is_major_reversal": 1, "event_id": opp.event_id}
        if ts in feats.index:
            row.update(feats.loc[ts].to_dict())
        true_rows.append(row)
    false_rows = []
    for fc in false_ctrl.itertuples(index=False):
        ts = pd.Timestamp(fc.timestamp)
        row = {"timestamp": ts, "direction": fc.direction, "label": fc.label, "is_major_reversal": 0, "event_id": ""}
        if ts in feats.index:
            row.update(feats.loc[ts].to_dict())
        false_rows.append(row)
    return pd.DataFrame(true_rows + false_rows)
