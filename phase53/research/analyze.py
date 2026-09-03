"""Descriptive analysis — univariate, G3 mechanism, good/bad."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase53.research.metrics import pf, summarize_r


def event_type_base_rates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    days = max((df["timestamp_ct"].max() - df["timestamp_ct"].min()).days, 1)
    for et, g in df.groupby("event_type"):
        rs = g["net_R"].astype(float)
        opp = g["opp_O2"].mean() if "opp_O2" in g.columns else np.nan
        row = {
            "EVENT TYPE": et,
            "N": len(g),
            "EVENTS/DAY": len(g) / days,
            "AVGR": float(rs.mean()),
            "PF": pf(rs),
            "OPPORTUNITY RATE": opp,
        }
        for side in ("LONG", "SHORT"):
            sub = g.loc[g["direction"] == side]
            row[f"{side} AVGR"] = float(sub["net_R"].mean()) if len(sub) else np.nan
        auth = g.loc[g["core_authorized"] == 1]
        unauth = g.loc[g["core_authorized"] == 0]
        row["CORE-AUTH AVGR"] = float(auth["net_R"].mean()) if len(auth) else np.nan
        row["CORE-UNAUTH AVGR"] = float(unauth["net_R"].mean()) if len(unauth) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def univariate_bins(df: pd.DataFrame, feature: str, train: pd.DataFrame, n_bins: int = 10) -> pd.DataFrame:
    tr = train[[feature, "net_R"]].dropna()
    if len(tr) < 100:
        return pd.DataFrame()
    qs = np.linspace(0, 1, n_bins + 1)
    edges = tr[feature].quantile(qs).values
    edges = np.unique(edges)
    if len(edges) < 3:
        return pd.DataFrame()
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sub = df.loc[(df[feature] >= lo) & (df[feature] <= hi)]
        if sub.empty:
            continue
        rs = sub["net_R"].astype(float)
        rows.append(
            {
                "feature": feature,
                "bin_lo": lo,
                "bin_hi": hi,
                "N": len(sub),
                "AvgR": float(rs.mean()),
                "PF": pf(rs),
                "win_rate": float((rs > 0).mean()),
                "MFE": float(sub["MFE_R"].mean()),
                "MAE": float(sub["MAE_R"].mean()),
                "opp_rate": float(sub["opp_O2"].mean()) if "opp_O2" in sub.columns else np.nan,
            }
        )
    return pd.DataFrame(rows)


def g3_mechanism_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """Failed range-break events vs continuous 15M range position."""
    sub = df.loc[df["event_type"].isin(["E13", "E14"])].copy()
    if sub.empty or "m15_range_pos_20" not in sub.columns:
        return pd.DataFrame()
    pos = sub["m15_range_pos_20"].astype(float)
    sub = sub.loc[pos.notna()].copy()
    sub["pos_decile"] = pd.qcut(sub["m15_range_pos_20"], 10, duplicates="drop")
    rows = []
    for dec, g in sub.groupby("pos_decile", observed=True):
        rs = g["net_R"].astype(float)
        rows.append(
            {
                "range_pos_decile": str(dec),
                "N": len(g),
                "AvgR": float(rs.mean()),
                "PF": pf(rs),
                "opp_rate": float(g["opp_O2"].mean()) if "opp_O2" in g.columns else np.nan,
            }
        )
    return pd.DataFrame(rows)


def good_bad_comparison(df: pd.DataFrame, threshold_r: float = 0.5) -> pd.DataFrame:
    good = df.loc[df["net_R"] >= threshold_r]
    bad = df.loc[df["net_R"] <= -0.5]
    if good.empty or bad.empty:
        return pd.DataFrame()
    from phase53.research.features import feature_columns

    rows = []
    for col in feature_columns(df):
        g = good[col].astype(float).dropna()
        b = bad[col].astype(float).dropna()
        if len(g) < 50 or len(b) < 50:
            continue
        pooled = float(np.sqrt((g.var() + b.var()) / 2)) or 1e-9
        d = (g.mean() - b.mean()) / pooled
        rows.append(
            {
                "feature": col,
                "good_mean": float(g.mean()),
                "bad_mean": float(b.mean()),
                "effect_size_d": float(d),
            }
        )
    return pd.DataFrame(rows).sort_values("effect_size_d", key=abs, ascending=False)


def feature_correlation(df: pd.DataFrame, cols: list[str], max_cols: int = 40) -> pd.DataFrame:
    use = [c for c in cols if c in df.columns][:max_cols]
    if len(use) < 2:
        return pd.DataFrame()
    corr = df[use].astype(float).corr()
    rows = []
    for i, a in enumerate(use):
        for b in use[i + 1 :]:
            rows.append({"feature_a": a, "feature_b": b, "correlation": float(corr.loc[a, b])})
    return pd.DataFrame(rows).sort_values("correlation", key=abs, ascending=False)
