"""Walk-forward predictive models — logistic regression."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from phase53.config import FEATURE_COUNTS, WALK_FORWARD_FOLDS
from phase53.research.metrics import max_dd, pf, summarize_r


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp_ct"])
    tz = ts.dt.tz
    lo, hi = pd.Timestamp(start, tz=tz), pd.Timestamp(end, tz=tz)
    return df.loc[(ts >= lo) & (ts <= hi)].copy()


def select_top_features(train: pd.DataFrame, features: list[str], target: str, k: int) -> list[str]:
    scores = []
    for f in features:
        sub = train[[f, target]].dropna()
        if len(sub) < 100:
            continue
        corr = sub[f].corr(sub[target])
        if np.isfinite(corr):
            scores.append((abs(corr), f))
    scores.sort(reverse=True)
    return [f for _, f in scores[:k]]


def walk_forward_models(
    df: pd.DataFrame,
    features: list[str],
    target: str = "opp_O2",
    max_features: int = 8,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns stitched OOS predictions, fold selections, decile table."""
    oos_parts: list[pd.DataFrame] = []
    selections: list[dict] = []
    feat_cols = [f for f in features if f in df.columns]

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train = _slice(df, tr_s, tr_e)
        test = _slice(df, te_s, te_e)
        if len(train) < 500 or len(test) < 100:
            continue
        sel_feats = select_top_features(train, feat_cols, target, max_features)
        if len(sel_feats) < 2:
            continue
        tr = train.dropna(subset=sel_feats + [target, "net_R"])
        te = test.dropna(subset=sel_feats + ["net_R"])
        if len(tr) < 300 or te.empty:
            continue
        X_tr = tr[sel_feats].astype(float).values
        y_tr = tr[target].astype(int).values
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        model = LogisticRegression(C=0.5, max_iter=500, class_weight="balanced")
        model.fit(X_tr_s, y_tr)
        X_te = te[sel_feats].astype(float).values
        prob = model.predict_proba(scaler.transform(X_te))[:, 1]
        part = te.copy()
        part["score"] = prob
        part["fold"] = fold_i
        oos_parts.append(part)
        selections.append({"fold": fold_i, "features": ",".join(sel_feats), "train_N": len(tr)})

    stitched = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    sel_df = pd.DataFrame(selections)
    deciles = score_deciles(stitched) if not stitched.empty else pd.DataFrame()
    return stitched, sel_df, deciles


def score_deciles(df: pd.DataFrame, score_col: str = "score") -> pd.DataFrame:
    if df.empty or score_col not in df.columns:
        return pd.DataFrame()
    sub = df.dropna(subset=[score_col, "net_R"]).copy()
    sub["decile"] = pd.qcut(sub[score_col], 10, labels=False, duplicates="drop") + 1
    rows = []
    for d, g in sub.groupby("decile"):
        rs = g["net_R"].astype(float)
        unauth = g.loc[g["core_authorized"] == 0]
        rows.append(
            {
                "DECILE": int(d),
                "N": len(g),
                "AVGR": float(rs.mean()),
                "PF": pf(rs),
                "WIN RATE": float((rs > 0).mean()),
                "OPPORTUNITY RATE": float(g["opp_O2"].mean()) if "opp_O2" in g.columns else np.nan,
                "MAE": float(g["MAE_R"].mean()),
                "MFE": float(g["MFE_R"].mean()),
                "CORE-UNAUTH AVGR": float(unauth["net_R"].mean()) if len(unauth) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def model_summary_row(df: pd.DataFrame, features: str, label: str = "P53") -> dict:
    sm = summarize_r(df)
    unauth = df.loc[df["core_authorized"] == 0] if "core_authorized" in df.columns else pd.DataFrame()
    long = df.loc[df["direction"] == "LONG"]
    short = df.loc[df["direction"] == "SHORT"]
    return {
        "MODEL": label,
        "FEATURES": features,
        "N": sm.get("N", 0),
        "TRADES/DAY": sm.get("trades_per_day", 0),
        "AVGR": sm.get("AvgR"),
        "PF": sm.get("PF"),
        "TOTALR": sm.get("TotalR"),
        "MAXDD": sm.get("MaxDD"),
        "LONG AVGR": float(long["net_R"].mean()) if len(long) else np.nan,
        "SHORT AVGR": float(short["net_R"].mean()) if len(short) else np.nan,
        "CORE-UNAUTH AVGR": float(unauth["net_R"].mean()) if len(unauth) else np.nan,
    }
