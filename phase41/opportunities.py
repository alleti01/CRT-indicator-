"""Post-hoc major reversal opportunity labeling (ground truth only)."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session

from .config import CLUSTER_BARS, LABEL_RISK_ATR, OPPORTUNITY_SENSITIVITY, PIVOT_LEFT, PIVOT_RIGHT, PRIMARY_OPPORTUNITY, RTH_SESSION


def _forward_path_metrics(
    market: pd.DataFrame,
    i: int,
    direction: int,
    *,
    risk_atr: float,
    max_bars: int,
) -> Dict[str, float]:
    """Forward excursion from bar i close in direction (+1 bull, -1 bear)."""
    atr = float(market.iloc[i]["atr"])
    risk = risk_atr * atr if atr > 0 else np.nan
    if not np.isfinite(risk) or risk <= 0:
        return {}
    entry = float(market.iloc[i]["close"])
    mfe = mae = 0.0
    bars_to = {k: np.nan for k in ("0.5", "1.0", "2.0")}
    hit_mfe_before_mae = False

    for elapsed, j in enumerate(range(i + 1, min(len(market), i + 1 + max_bars)), start=1):
        bar = market.iloc[j]
        hi, lo = float(bar.high), float(bar.low)
        if direction == 1:
            fav = (hi - entry) / risk
            adv = (entry - lo) / risk
        else:
            fav = (entry - lo) / risk
            adv = (hi - entry) / risk
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        for lvl, key in ((0.5, "0.5"), (1.0, "1.0"), (2.0, "2.0")):
            if np.isnan(bars_to[key]) and mfe >= lvl:
                bars_to[key] = elapsed
        if mfe >= PRIMARY_OPPORTUNITY["mfe_r"] and mae < PRIMARY_OPPORTUNITY["mae_r"]:
            hit_mfe_before_mae = True
        if mae >= PRIMARY_OPPORTUNITY["mae_r"] and mfe < PRIMARY_OPPORTUNITY["mfe_r"]:
            break

    return {
        "MFE_R": mfe,
        "MAE_R": mae,
        "bars_to_0.5R": bars_to["0.5"],
        "bars_to_1R": bars_to["1.0"],
        "bars_to_2R": bars_to["2.0"],
        "primary_hit": hit_mfe_before_mae or (mfe >= PRIMARY_OPPORTUNITY["mfe_r"] and mae < PRIMARY_OPPORTUNITY["mae_r"]),
    }


def _is_local_extreme(market: pd.DataFrame, i: int, kind: str) -> bool:
    w = PIVOT_LEFT + PIVOT_RIGHT + 1
    lo = max(0, i - PIVOT_LEFT)
    hi = min(len(market), i + PIVOT_RIGHT + 1)
    window = market.iloc[lo:hi]
    if kind == "low":
        return float(market.iloc[i]["low"]) <= float(window["low"].min())
    return float(market.iloc[i]["high"]) >= float(window["high"].max())


def _qualifies(spec: dict, mfe: float, mae: float, max_bars: int, i: int, market: pd.DataFrame, direction: int) -> bool:
    """Check if MFE/MAE path meets opportunity spec within hold window."""
    risk = LABEL_RISK_ATR * float(market.iloc[i]["atr"])
    if risk <= 0:
        return False
    entry = float(market.iloc[i]["close"])
    mfe_r = mae_r = 0.0
    for j in range(i + 1, min(len(market), i + 1 + max_bars)):
        bar = market.iloc[j]
        hi, lo = float(bar.high), float(bar.low)
        if direction == 1:
            mfe_r = max(mfe_r, (hi - entry) / risk)
            mae_r = max(mae_r, (entry - lo) / risk)
        else:
            mfe_r = max(mfe_r, (entry - lo) / risk)
            mae_r = max(mae_r, (hi - entry) / risk)
        if mfe_r >= spec["mfe_r"] and mae_r < spec["mae_r"]:
            return True
        if mae_r >= spec["mae_r"] and mfe_r < spec["mfe_r"]:
            return False
    return mfe_r >= spec["mfe_r"] and mae_r < spec["mae_r"]


def label_opportunities(market: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (opportunities, sensitivity_table)."""
    rth_mask = pd.Series([is_in_session(ts, RTH_SESSION) for ts in market.index], index=market.index)
    m = market.loc[rth_mask].copy()
    pos = {ts: i for i, ts in enumerate(market.index)}

    raw: List[dict] = []
    for i in range(PIVOT_LEFT, len(m) - PIVOT_RIGHT - PRIMARY_OPPORTUNITY["hold_bars"]):
        ts = m.index[i]
        gi = pos[ts]
        if _is_local_extreme(m, i, "low"):
            direction = 1
            extreme_px = float(m.iloc[i]["low"])
        elif _is_local_extreme(m, i, "high"):
            direction = -1
            extreme_px = float(m.iloc[i]["high"])
        else:
            continue
        path = _forward_path_metrics(market, gi, direction, risk_atr=LABEL_RISK_ATR, max_bars=8)
        if not path:
            continue
        spec_hits = {s["label"]: _qualifies(s, path["MFE_R"], path["MAE_R"], s["hold_bars"], gi, market, direction) for s in OPPORTUNITY_SENSITIVITY}
        if not spec_hits[PRIMARY_OPPORTUNITY["label"]]:
            continue
        raw.append(
            {
                "extreme_timestamp": ts,
                "direction": "Long" if direction == 1 else "Short",
                "extreme_price": extreme_px,
                "atr_at_extreme": float(m.iloc[i]["atr"]),
                **path,
                **{f"hit_{k}": v for k, v in spec_hits.items()},
            }
        )

    if not raw:
        return pd.DataFrame(), pd.DataFrame()

    df = pd.DataFrame(raw).sort_values("extreme_timestamp").reset_index(drop=True)
    # Cluster nearby same-direction events
    clustered: List[dict] = []
    i = 0
    eid = 0
    while i < len(df):
        eid += 1
        grp = [df.iloc[i]]
        j = i + 1
        while j < len(df):
            if (
                df.iloc[j]["direction"] == grp[0]["direction"]
                and (df.iloc[j]["extreme_timestamp"] - grp[-1]["extreme_timestamp"]) <= pd.Timedelta(minutes=15 * CLUSTER_BARS)
            ):
                grp.append(df.iloc[j])
                j += 1
            else:
                break
        # keep earliest extreme in cluster
        if grp[0]["direction"] == "Long":
            best = min(grp, key=lambda r: r["extreme_price"])
        else:
            best = max(grp, key=lambda r: r["extreme_price"])
        row = dict(best)
        row["event_id"] = f"MR{eid:05d}"
        row["cluster_size"] = len(grp)
        clustered.append(row)
        i = j

    opp = pd.DataFrame(clustered)
    sens = pd.DataFrame(
        [{"label": s["label"], "count": int(opp[f"hit_{s['label']}"].sum()), "rate": float(opp[f"hit_{s['label']}"].mean())} for s in OPPORTUNITY_SENSITIVITY]
    )
    return opp, sens
