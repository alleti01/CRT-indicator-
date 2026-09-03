"""Phase58F analysis outputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics


def policy_metrics(trades: pd.DataFrame, decisions: pd.Series, policy: str) -> dict:
    """Metrics for kept trades under a policy."""
    t = trades.copy()
    t["decision"] = decisions.values
    kept = t.loc[t["decision"] == "KEEP"]
    abst = t.loc[t["decision"] == "ABSTAIN"]

    mk = metrics(kept["net_R"].values) if not kept.empty else dict(N=0, AvgR=0, PF=0, TotalR=0, MaxDD=0, WinRate=0)
    ab = metrics(abst["net_R"].values) if not abst.empty else dict(N=0, AvgR=0, PF=0, TotalR=0)

    winners = t.loc[t["net_R"] > 0]
    losers = t.loc[t["net_R"] <= 0]
    wr = len(kept.loc[kept["net_R"] > 0]) / len(winners) * 100 if len(winners) else 0
    lr = len(abst.loc[abst["net_R"] <= 0]) / len(losers) * 100 if len(losers) else 0

    neg_avoided = -abst.loc[abst["net_R"] <= 0, "net_R"].sum() if not abst.empty else 0
    pos_destroyed = kept.loc[kept.index.isin(abst.index) & (kept["net_R"] > 0), "net_R"].sum() if not abst.empty else 0
    # positive R destroyed = sum of net_R for winners that were abstained
    pos_destroyed = abst.loc[abst["net_R"] > 0, "net_R"].sum() if not abst.empty else 0
    neg_avoided = abs(abst.loc[abst["net_R"] <= 0, "net_R"].sum()) if not abst.empty else 0
    sel = neg_avoided / pos_destroyed if pos_destroyed > 0 else float("inf") if neg_avoided > 0 else 0

    false_rev = t.loc[(t.get("false_reversal_risk", pd.Series("", index=t.index)) == "HIGH")]
    fr_removed = len(abst.loc[abst.index.isin(false_rev.index)]) if len(false_rev) else 0

    return {
        "policy": policy,
        "trades": mk.get("N", 0),
        "abstained": len(abst),
        "AvgR": mk.get("AvgR", 0),
        "PF": mk.get("PF", 0),
        "TotalR": mk.get("TotalR", 0),
        "MaxDD": mk.get("MaxDD", 0),
        "WinRate": mk.get("WinRate", 0),
        "winners_retained_pct": wr,
        "losers_removed_pct": lr,
        "abstained_AvgR": ab.get("AvgR", 0),
        "abstained_TotalR": ab.get("TotalR", 0),
        "negative_R_avoided": neg_avoided,
        "positive_R_destroyed": pos_destroyed,
        "selectivity_ratio": sel,
        "false_reversals_removed": fr_removed,
    }


def confidence_band_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    order = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]
    for band in order:
        sub = df.loc[df["direction_confidence_band"] == band]
        if sub.empty:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({
            "confidence_band": band,
            "count": len(sub),
            "win_rate": m.get("WinRate", 0),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
        })
    return pd.DataFrame(rows)


def confidence_retention_curve(trades: pd.DataFrame) -> pd.DataFrame:
    """Progressively abstain lower confidence bands."""
    order = ["VERY_LOW", "LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
    rows = []
    abstain_bands: set[str] = set()
    for step in range(len(order) + 1):
        if step > 0:
            abstain_bands.add(order[step - 1])
        kept = trades.loc[~trades["direction_confidence_band"].isin(abstain_bands)]
        abst = trades.loc[trades["direction_confidence_band"].isin(abstain_bands)]
        m = metrics(kept["net_R"].values) if not kept.empty else {}
        neg = abs(abst.loc[abst["net_R"] <= 0, "net_R"].sum()) if not abst.empty else 0
        pos = abst.loc[abst["net_R"] > 0, "net_R"].sum() if not abst.empty else 0
        rows.append({
            "step": step,
            "abstain_bands": ",".join(sorted(abstain_bands)) if abstain_bands else "none",
            "trades_retained": len(kept),
            "AvgR": m.get("AvgR", 0),
            "TotalR": m.get("TotalR", 0),
            "selectivity_ratio": neg / pos if pos > 0 else float("inf") if neg > 0 else 0,
        })
    return pd.DataFrame(rows)


def good_location_confidence(trades: pd.DataFrame, loc_thr: int = 2) -> pd.DataFrame:
    good = trades.loc[trades["location_score"] >= loc_thr]
    rows = []
    for band in ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]:
        sub = good.loc[good["direction_confidence_band"] == band]
        if sub.empty:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({"confidence_band": band, "trades": len(sub), **m})
    return pd.DataFrame(rows)


def confidence_direction_matrix(trades: pd.DataFrame, loc_thr: int = 2) -> pd.DataFrame:
    """Evaluation-only direction quality matrix."""
    t = trades.copy()
    t["dir_good"] = t["net_R"] > 0
    t["loc_good"] = t["location_score"] >= loc_thr
    rows = []
    for band in ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]:
        for loc in [True, False]:
            sub = t.loc[(t["direction_confidence_band"] == band) & (t["loc_good"] == loc)]
            dg = sub.loc[sub["dir_good"]]
            db = sub.loc[~sub["dir_good"]]
            rows.append({
                "confidence_band": band,
                "location": "GOOD" if loc else "WEAK",
                "direction_good_count": len(dg),
                "direction_bad_count": len(db),
                "direction_good_TotalR": dg["net_R"].sum() if len(dg) else 0,
                "direction_bad_TotalR": db["net_R"].sum() if len(db) else 0,
            })
    return pd.DataFrame(rows)


def check_monotonicity(band_table: pd.DataFrame) -> bool:
    if band_table.empty or len(band_table) < 3:
        return False
    order = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]
    bt = band_table.set_index("confidence_band").reindex([b for b in order if b in band_table["confidence_band"].values])
    avgs = bt["AvgR"].values
    return bool(np.all(avgs[:-1] >= avgs[1:] - 0.05))  # allow small noise
