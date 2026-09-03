"""Walk-forward quality scoring."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from phase31.metrics import performance

from .config import REJECTION_RATES, WALK_FORWARD_FOLDS
from .features import available_feature_cols


def _prep_xy(df: pd.DataFrame, cols: List[str], target: str = "net_R") -> Tuple[pd.DataFrame, np.ndarray]:
    x = df[cols].astype(float).replace([np.inf, -np.inf], np.nan)
    med = x.median()
    x = x.fillna(med)
    y = df[target].astype(float).values
    return x, y


def _to_score(raw: np.ndarray, lo: float, hi: float) -> np.ndarray:
    if hi <= lo:
        return np.full_like(raw, 50.0, dtype=float)
    s = (raw - lo) / (hi - lo) * 100.0
    return np.clip(s, 0, 100)


def _screen_features(train: pd.DataFrame, cols: List[str], target: str = "net_R") -> pd.DataFrame:
    rows = []
    for c in cols:
        sub = train[[c, target]].dropna()
        if len(sub) < 30:
            continue
        rho, _ = spearmanr(sub[c], sub[target])
        rows.append({"feature": c, "spearman": float(rho) if np.isfinite(rho) else 0.0})
    return pd.DataFrame(rows).sort_values("spearman", key=abs, ascending=False)


def _pick_train_reject_rate(train: pd.DataFrame, scores: np.ndarray) -> float:
    """Select rejection rate on TRAIN only."""
    best_rate = 0.0
    best_avgr = performance(train, col="net_R").get("AvgR", 0)
    order = np.argsort(scores)
    n = len(train)
    for rate in REJECTION_RATES:
        n_rej = int(round(n * rate))
        keep_idx = order[n_rej:]
        if len(keep_idx) < n * 0.5:
            continue
        sub = train.iloc[keep_idx]
        avgr = performance(sub, col="net_R").get("AvgR", 0)
        if avgr > best_avgr + 0.02:
            best_avgr = avgr
            best_rate = rate
    return best_rate


def walk_forward_quality(
    dataset: pd.DataFrame,
    *,
    target: str = "net_R",
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    cols = available_feature_cols(dataset)
    oos_parts = []
    selections = []

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
        if len(train) < 80 or len(test) < 20:
            continue

        screened = _screen_features(train, cols, target=target)
        top_feats = screened.head(8)["feature"].tolist() if not screened.empty else cols[:8]
        Xtr, ytr = _prep_xy(train, top_feats, target=target)
        Xte, yte = _prep_xy(test, top_feats, target=target)

        scaler = StandardScaler()
        Xtr_s = scaler.fit_transform(Xtr)
        Xte_s = scaler.transform(Xte)

        ridge = Ridge(alpha=1.0)
        ridge.fit(Xtr_s, ytr)
        pred_tr = ridge.predict(Xtr_s)
        pred_te = ridge.predict(Xte_s)

        lo, hi = float(np.quantile(pred_tr, 0.05)), float(np.quantile(pred_tr, 0.95))
        q_tr = _to_score(pred_tr, lo, hi)
        q_ml = _to_score(pred_te, lo, hi)

        reject_rate = _pick_train_reject_rate(
            train.assign(_qs=q_tr),
            q_tr,
        )
        train_rej_n = int(round(len(train) * reject_rate))
        test_rej_n = int(round(len(test) * reject_rate))
        test_order = np.argsort(q_ml)
        test_keep = set(test_order[test_rej_n:])

        # Simple score: rank-sum of top 3 stable features by train spearman sign
        simple_cols = screened.head(3)["feature"].tolist()
        simple_raw = np.zeros(len(test))
        for _, row in screened.head(3).iterrows():
            c = row["feature"]
            sign = 1.0 if row["spearman"] >= 0 else -1.0
            vals = test[c].astype(float).fillna(train[c].median()).values
            ranks = pd.Series(vals).rank(pct=True).values
            simple_raw += sign * ranks
        lo_s, hi_s = np.quantile(simple_raw, 0.05), np.quantile(simple_raw, 0.95)
        q_simple = _to_score(simple_raw, lo_s, hi_s)

        part = test.copy()
        part["fold"] = fold_i
        part["quality_score"] = q_ml
        part["quality_score_simple"] = q_simple
        part["quality_pred_R"] = pred_te
        part["train_reject_rate"] = reject_rate
        part["filter_keep"] = [i in test_keep for i in range(len(test))]
        oos_parts.append(part)

        coef_map = {c: float(w) for c, w in zip(top_feats, ridge.coef_)}
        selections.append(
            {
                "fold": fold_i,
                "features": ",".join(top_feats),
                "top_simple_features": ",".join(simple_cols),
                "train_reject_rate": reject_rate,
                "train_spearman_top": float(screened.iloc[0]["spearman"]) if len(screened) else np.nan,
                "ridge_intercept": float(ridge.intercept_),
                **{f"w_{k}": v for k, v in list(coef_map.items())[:5]},
            }
        )

    oos = pd.concat(oos_parts, ignore_index=True) if oos_parts else pd.DataFrame()
    return oos, pd.DataFrame(selections), pd.DataFrame()


def walk_forward_by_segment(dataset: pd.DataFrame, segment_col: str, segment_val: str) -> pd.DataFrame:
    sub = dataset.loc[dataset[segment_col] == segment_val]
    oos, _, _ = walk_forward_quality(sub)
    return oos
