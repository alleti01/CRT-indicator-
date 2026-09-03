"""Export frozen S54 specification artifacts and fold models."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase53.config import WALK_FORWARD_FOLDS
from phase53.research.features import feature_columns
from phase53.research.models import _slice, select_top_features
from phase55.config import (
    FROZEN,
    HOLDOUT_END,
    HOLDOUT_START,
    MAX_HOLD_MIN,
    P53_REF,
    S54_EPISODE_FAMILY,
    S54_ENTRY_RULE,
    S54_TIME_WINDOW_MIN,
    STOP_ATR,
    TARGET_R,
)


def _holdout_mask(ts: pd.Series) -> pd.Series:
    return (ts >= pd.Timestamp(HOLDOUT_START, tz=ts.dt.tz)) & (ts <= pd.Timestamp(HOLDOUT_END, tz=ts.dt.tz))


def export_fold_models(scored: pd.DataFrame, feats: list[str]) -> tuple[pd.DataFrame, list[dict]]:
    models: list[dict] = []
    for fold_i, (tr_s, tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        train = _slice(scored, tr_s, tr_e)
        test = _slice(scored, te_s, te_e)
        if len(train) < 500:
            continue
        sel = select_top_features(train, feats, "opp_O2", 8)
        tr = train.dropna(subset=sel + ["opp_O2"])
        if len(tr) < 300:
            continue
        scaler = StandardScaler()
        X = scaler.fit_transform(tr[sel].astype(float).values)
        model = LogisticRegression(C=0.5, max_iter=500, class_weight="balanced")
        model.fit(X, tr["opp_O2"].astype(int).values)
        blob = {"fold": fold_i, "features": sel, "scaler": scaler, "model": model, "test_start": te_s, "test_end": te_e}
        joblib.dump(blob, FROZEN / f"fold_{fold_i}_model.joblib")
        models.append(
            {
                "fold": fold_i,
                "features": sel,
                "test_start": te_s,
                "test_end": te_e,
                "coef": model.coef_.tolist(),
                "intercept": model.intercept_.tolist(),
                "scaler_mean": scaler.mean_.tolist(),
                "scaler_scale": scaler.scale_.tolist(),
            }
        )
    return pd.DataFrame(models), models


def export_all(scored_path: Path | None = None) -> str:
    FROZEN.mkdir(parents=True, exist_ok=True)
    from phase55.config import P54_SCORED_CACHE, PHASE53_PARQUET

    if scored_path and scored_path.exists():
        scored = pd.read_parquet(scored_path)
    elif P54_SCORED_CACHE.exists():
        scored = pd.read_parquet(P54_SCORED_CACHE)
    else:
        from phase54.research.parity import assign_scores, load_events

        all_ev = load_events()
        ts = pd.to_datetime(all_ev["timestamp_ct"])
        pre = all_ev.loc[~_holdout_mask(ts)]
        scored, _ = assign_scores(pre)

    feats = feature_columns(scored)
    model_df, model_specs = export_fold_models(scored, feats)

    # D10 qcut bin edges (frozen on pre-holdout scored pool)
    scores = scored["score"].dropna().astype(float)
    _, bins = pd.qcut(scores, 10, retbins=True, duplicates="drop")
    d10_min_score = float(bins[-2]) if len(bins) >= 2 else float(scores.quantile(0.9))

    feature_spec = {
        "feature_columns": feats,
        "swing": 5,
        "displacement_body_mult": 1.5,
        "htf_alignment": "last_completed_bar",
        "session": "America/Chicago",
        "rth": "0930-1600",
    }
    model_spec = {
        "type": "LogisticRegression",
        "C": 0.5,
        "max_iter": 500,
        "class_weight": "balanced",
        "target": "opp_O2",
        "max_features": 8,
        "selection": "abs_pearson_corr_train",
        "folds": model_df.to_dict(orient="records"),
    }
    score_spec = {
        "method": "predict_proba_positive_class",
        "d10_method": "global_qcut_decile_10_preholdout",
        "qcut_bin_edges": [float(x) for x in bins],
        "d10_min_score_inclusive": d10_min_score,
        "top20_quantile": 0.8,
    }
    episode_spec = {
        "family": S54_EPISODE_FAMILY,
        "window_min": S54_TIME_WINDOW_MIN,
        "same_direction_rule": "gap_minutes <= window suppresses",
        "opposite_direction": "independent_per_direction",
        "entry": S54_ENTRY_RULE,
    }
    execution_spec = {
        "stop_atr": STOP_ATR,
        "target_r": TARGET_R,
        "max_hold_min": MAX_HOLD_MIN,
        "entry_price": "signal_bar_close",
        "sim_start_bar": "entry_i_plus_1",
        "intrabar_order": "stop_before_target",
        "time_exit": "close_of_last_hold_bar",
        "cost": "phase45_round_turn",
    }

    for name, spec in [
        ("phase53_feature_spec.json", feature_spec),
        ("phase53_model_spec.json", model_spec),
        ("phase53_score_spec.json", score_spec),
        ("phase54_episode_spec.json", episode_spec),
        ("s54_execution_spec.json", execution_spec),
    ]:
        (FROZEN / name).write_text(json.dumps(spec, indent=2) + "\n")

    payload = json.dumps(
        {
            "feature_spec": feature_spec,
            "model_spec": {k: v for k, v in model_spec.items() if k != "folds"},
            "score_spec": score_spec,
            "episode_spec": episode_spec,
            "execution_spec": execution_spec,
            "p53_ref": P53_REF,
        },
        sort_keys=True,
    )
    model_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
    (FROZEN / "model_hash.txt").write_text(model_hash + "\n")
    return model_hash


if __name__ == "__main__":
    print(export_all())
