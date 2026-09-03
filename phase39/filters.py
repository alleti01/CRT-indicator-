"""Walk-forward filter research and retention frontier."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance

from .config import PRIMARY_MOVEMENT_MFE_R, RETENTION_LEVELS, WALK_FORWARD_FOLDS


FEATURE_COLS = [
    "body_atr",
    "range_atr",
    "atr_percentile",
    "atr_expansion",
    "atr_short_long_ratio",
    "rel_volume",
    "close_loc",
    "upper_wick_ratio",
    "lower_wick_ratio",
    "pre_entry_move_3_atr",
    "pre_entry_move_5_atr",
    "pre_entry_efficiency_5",
    "impulse_3bar",
    "directional_efficiency",
    "overlap_density_5",
    "alternating_bars_8",
    "inside_bar_density_8",
    "dist_session_high_atr",
    "dist_session_low_atr",
    "session_travel_atr",
    "avg_range_3_atr",
    "avg_range_5_atr",
    "price_vs_ema8",
    "ema8_slope",
]


def _prep_xy(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    cols = [c for c in FEATURE_COLS if c in df.columns]
    x = df[cols].astype(float).replace([np.inf, -np.inf], np.nan)
    med = x.median()
    x = x.fillna(med)
    y = df["meaningful_expansion"].astype(int)
    return x, y, cols


def walk_forward_static_model(dataset: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict]:
    from sklearn.ensemble import ExtraTreesClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.preprocessing import StandardScaler

    rows = []
    oos_preds = []
    feat_importance: Dict[str, List[float]] = {}

    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, start=1):
        tz = dataset["marker_bar_timestamp"].dt.tz
        train = dataset.loc[
            (dataset["marker_bar_timestamp"] >= pd.Timestamp(tr_s, tz=tz))
            & (dataset["marker_bar_timestamp"] <= pd.Timestamp(tr_e, tz=tz))
        ]
        test = dataset.loc[
            (dataset["marker_bar_timestamp"] >= pd.Timestamp(te_s, tz=tz))
            & (dataset["marker_bar_timestamp"] <= pd.Timestamp(te_e, tz=tz))
        ]
        if len(train) < 100 or len(test) < 20:
            continue
        Xtr, ytr, cols = _prep_xy(train)
        Xte, yte, _ = _prep_xy(test)
        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xtr)
        Xte_s = scaler.transform(Xte)

        lr = LogisticRegression(max_iter=500, class_weight="balanced")
        lr.fit(Xtr_s, ytr)
        p_lr = lr.predict_proba(Xte_s)[:, 1]
        auc_lr = roc_auc_score(yte, p_lr) if yte.nunique() > 1 else np.nan

        et = ExtraTreesClassifier(n_estimators=200, max_depth=4, random_state=42, class_weight="balanced")
        et.fit(Xtr, ytr)
        p_et = et.predict_proba(Xte)[:, 1]
        auc_et = roc_auc_score(yte, p_et) if yte.nunique() > 1 else np.nan

        for c, imp in zip(cols, et.feature_importances_):
            feat_importance.setdefault(c, []).append(float(imp))

        pred = test.copy()
        pred["fold"] = fold_i
        pred["p_expansion_lr"] = p_lr
        pred["p_expansion_et"] = p_et
        pred["y_expansion"] = yte.values
        oos_preds.append(pred)

        rows.append({"fold": fold_i, "train_N": len(train), "test_N": len(test), "auc_lr": auc_lr, "auc_et": auc_et})

    wf = pd.DataFrame(rows)
    oos = pd.concat(oos_preds, ignore_index=True) if oos_preds else pd.DataFrame()

    stable = (
        pd.DataFrame(
            [{"feature": k, "mean_importance": float(np.mean(v)), "folds": len(v)} for k, v in feat_importance.items()]
        )
        .sort_values("mean_importance", ascending=False)
        .reset_index(drop=True)
    )
    meta = {"mean_auc_lr": float(wf["auc_lr"].mean()) if not wf.empty else np.nan, "mean_auc_et": float(wf["auc_et"].mean()) if not wf.empty else np.nan}
    return wf, oos, stable, meta


def simple_filter_search(oos: pd.DataFrame, paths: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """Train-only threshold rules on OOS predictions + feature quantiles."""
    path_cols = paths[["signal_id", "realized_R", "signal_type", "marker_bar_timestamp"]].rename(
        columns={"realized_R": "realized_R_path", "signal_type": "signal_type_path"}
    )
    merged = oos.merge(path_cols, on="signal_id", how="left")
    if "realized_R" not in merged.columns:
        merged["realized_R"] = merged["realized_R_path"]
    if merged.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    merged["net_R"] = merged["realized_R"]  # costs applied later in run
    baseline = performance(merged, col="net_R")

    # Best simple rule: keep if model p_expansion >= median on OOS stitched
    cutoff = merged["p_expansion_et"].quantile(0.35)
    keep = merged.loc[merged["p_expansion_et"] >= cutoff]
    filtered = performance(keep, col="net_R")

    frontier_rows = []
    for ret in RETENTION_LEVELS:
        thr = merged["p_expansion_et"].quantile(1 - ret)
        sub = merged.loc[merged["p_expansion_et"] >= thr]
        if sub.empty:
            continue
        p = performance(sub, col="net_R")
        frontier_rows.append({"retention_pct": ret, "threshold": thr, "N": p["N"], "AvgR": p["AvgR"], "PF": p["PF"], "MaxDD": p["MaxDD"]})

    rule = {
        "type": "p_expansion_et",
        "threshold": float(cutoff),
        "description": f"Keep if ExtraTrees expansion probability >= {cutoff:.3f}",
        "baseline": baseline,
        "filtered": filtered,
        "retention": len(keep) / len(merged),
    }
    return pd.DataFrame([rule]), pd.DataFrame(frontier_rows), rule


def segment_performance(df: pd.DataFrame, col: str = "net_R") -> pd.DataFrame:
    rows = []
    for st in sorted(df["signal_type"].unique()):
        sub = df.loc[df["signal_type"] == st]
        rows.append({"segment": st, **performance(sub, col=col)})
    for arch, subdf in (("continuation", df[df["signal_type"].isin(["L", "S"])]), ("reversal", df[df["signal_type"].isin(["RL", "RS"])])):
        if not subdf.empty:
            rows.append({"segment": arch, **performance(subdf, col=col)})
    rows.append({"segment": "ALL", **performance(df, col=col)})
    return pd.DataFrame(rows)
