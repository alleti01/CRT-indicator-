"""Walk-forward analysis, combination research, and quality model."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from phase53.research.metrics import pf, summarize_r
from phase57.config import HOLDOUT_START, WALK_FORWARD_FOLDS
from phase57.research.outcomes import batch_simulate
from phase57.research.registry import register


def _ts_col(df: pd.DataFrame) -> str:
    for c in ("timestamp_ct", "setup_ts", "formation_ts", "entry_ts"):
        if c in df.columns:
            return c
    return df.columns[0]


def _slice(df: pd.DataFrame, start: str, end: str, ts_col: str) -> pd.DataFrame:
    ts = pd.to_datetime(df[ts_col])
    tz = ts.iloc[0].tz if len(ts) and hasattr(ts.iloc[0], "tz") else None
    return df.loc[(ts >= pd.Timestamp(start, tz=tz)) & (ts <= pd.Timestamp(end, tz=tz))]


def walk_forward_evaluate(
    m1: pd.DataFrame,
    events: pd.DataFrame,
    *,
    family: str = "",
    hypothesis: str = "",
    parameters: str = "",
    entry_col: str = "entry_i",
    dir_col: str = "direction",
) -> dict:
    """Run WF evaluation: compute TRAIN and stitched OOS metrics."""
    tc = _ts_col(events)
    oos_parts = []
    train_parts = []
    for tr_s, tr_e, te_s, te_e in WALK_FORWARD_FOLDS:
        train = _slice(events, tr_s, tr_e, tc)
        test = _slice(events, te_s, te_e, tc)
        train_parts.append(train)
        oos_parts.append(test)
    train_all = pd.concat(train_parts, ignore_index=True).drop_duplicates(subset=[entry_col, tc])
    oos_all = pd.concat(oos_parts, ignore_index=True).drop_duplicates(subset=[entry_col, tc])

    train_trades = batch_simulate(m1, train_all.rename(columns={entry_col: "entry_i", dir_col: "direction"})) if not train_all.empty else pd.DataFrame()
    oos_trades = batch_simulate(m1, oos_all.rename(columns={entry_col: "entry_i", dir_col: "direction"})) if not oos_all.empty else pd.DataFrame()

    tm = summarize_r(train_trades.assign(timestamp_ct=train_all[tc].values[:len(train_trades)])) if not train_trades.empty else {"N": 0}
    om = summarize_r(oos_trades.assign(timestamp_ct=oos_all[tc].values[:len(oos_trades)])) if not oos_trades.empty else {"N": 0}

    config_id = register(
        family=family,
        hypothesis=hypothesis,
        parameters=parameters,
        train_metrics=tm,
        oos_metrics=om,
    )
    return {"config_id": config_id, "train": tm, "oos": om}


def build_quality_model(
    m1: pd.DataFrame,
    events: pd.DataFrame,
    feature_cols: list[str],
    target_col: str = "net_R",
    *,
    entry_col: str = "entry_i",
    dir_col: str = "direction",
) -> tuple[pd.DataFrame, dict]:
    """Simple logistic regression quality model on event features.

    Returns scored events (with 'quality_score') and model summary.
    """
    tc = _ts_col(events)
    ev = events.dropna(subset=feature_cols).copy()
    if ev.empty or len(ev) < 200:
        return ev, {"status": "INSUFFICIENT_DATA"}

    # Simulate trades to get outcome
    trades = batch_simulate(m1, ev.rename(columns={entry_col: "entry_i", dir_col: "direction"}))
    if trades.empty:
        return ev, {"status": "NO_TRADES"}
    ev = ev.iloc[:len(trades)].copy()
    ev["trade_net_R"] = trades["net_R"].values
    ev["target"] = (ev["trade_net_R"] > 0).astype(int)

    # Walk-forward scoring
    scored_parts = []
    for tr_s, tr_e, te_s, te_e in WALK_FORWARD_FOLDS:
        train = _slice(ev, tr_s, tr_e, tc)
        test = _slice(ev, te_s, te_e, tc)
        if len(train) < 100 or test.empty:
            continue
        tr_clean = train.dropna(subset=feature_cols + ["target"])
        if len(tr_clean) < 50:
            continue
        X_tr = tr_clean[feature_cols].astype(float).values
        y_tr = tr_clean["target"].values
        scaler = StandardScaler()
        X_tr_s = scaler.fit_transform(X_tr)
        model = LogisticRegression(C=0.5, max_iter=500, class_weight="balanced")
        model.fit(X_tr_s, y_tr)
        te_clean = test.dropna(subset=feature_cols)
        if te_clean.empty:
            continue
        X_te = te_clean[feature_cols].astype(float).values
        te_clean = te_clean.copy()
        te_clean["quality_score"] = model.predict_proba(scaler.transform(X_te))[:, 1]
        scored_parts.append(te_clean)

    if not scored_parts:
        return ev, {"status": "NO_SCORED_FOLDS"}
    scored = pd.concat(scored_parts, ignore_index=True)

    # Decile analysis for monotonicity check
    scored["decile"] = pd.qcut(scored["quality_score"], 10, labels=False, duplicates="drop") + 1
    decile_rows = []
    for d, g in scored.groupby("decile"):
        decile_rows.append({"decile": int(d), "N": len(g), "AvgR": float(g["trade_net_R"].mean()), "win_rate": float((g["trade_net_R"] > 0).mean())})
    decile_df = pd.DataFrame(decile_rows)
    monotonic = False
    if len(decile_df) >= 5:
        corr = decile_df["decile"].corr(decile_df["AvgR"])
        monotonic = corr > 0.5

    return scored, {"status": "OK", "scored_N": len(scored), "monotonic": monotonic, "deciles": decile_df.to_dict(orient="records")}
