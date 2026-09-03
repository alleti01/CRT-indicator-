"""Walk-forward OOS validation for Phase 44 simple score."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from phase31.metrics import performance

from .config import REJECT_BOTTOM_PCT, WALK_FORWARD_FOLDS
from .features import normalize_score, simple_raw


def _calibrate_train(train: pd.DataFrame) -> dict:
    raw = train["pine_simple_raw"].astype(float).values
    q05 = float(np.quantile(raw, 0.05))
    q95 = float(np.quantile(raw, 0.95))
    score = normalize_score(raw, q05, q95)
    thr = float(np.quantile(score, REJECT_BOTTOM_PCT))
    return {
        "train_q05": q05,
        "train_q95": q95,
        "train_threshold": thr,
        "train_tier_a_plus": float(np.quantile(score, 0.80)),
        "train_tier_a": float(np.quantile(score, 0.60)),
        "train_tier_b": thr,
    }


def _apply_params(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    out = df.copy()
    raw = out["pine_simple_raw"].astype(float).values
    score = normalize_score(raw, params["train_q05"], params["train_q95"])
    out["simple_raw"] = raw
    out["quality_score"] = score
    out["quality_pass"] = score >= params["train_threshold"]
    out["confidence"] = np.where(
        ~out["quality_pass"],
        "C",
        np.where(score >= params["train_tier_a_plus"], "A+", np.where(score >= params["train_tier_a"], "A", "B")),
    )
    for k, v in params.items():
        out[k] = v
    return out


def walk_forward_validate(dataset: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    fold_rows = []
    test_parts = []

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
        if len(train) < 50 or len(test) < 10:
            continue
        params = _calibrate_train(train)
        scored = _apply_params(test, params)
        scored["fold"] = fold_i
        test_parts.append(scored)
        acc = scored.loc[scored["quality_pass"]]
        fold_rows.append(
            {
                "fold": fold_i,
                "train_start": tr_s,
                "train_end": tr_e,
                "test_start": te_s,
                "test_end": te_e,
                "train_N": len(train),
                "test_N": len(test),
                **params,
                "test_accepted_N": len(acc),
                "test_rejected_N": len(test) - len(acc),
                "test_retention": len(acc) / len(test) if len(test) else 0,
                "test_AvgR": performance(acc, col="net_R").get("AvgR", 0) if len(acc) else np.nan,
                "test_PF": performance(acc, col="net_R").get("PF", 0) if len(acc) else np.nan,
                "test_baseline_AvgR": performance(test, col="net_R").get("AvgR", 0),
            }
        )

    folds = pd.DataFrame(fold_rows)
    oos = pd.concat(test_parts, ignore_index=True) if test_parts else pd.DataFrame()
    return folds, oos, oos.loc[oos["quality_pass"]].copy() if not oos.empty else pd.DataFrame()
