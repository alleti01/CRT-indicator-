"""Frozen Phase53 score application and D10 qualification."""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from phase53.config import WALK_FORWARD_FOLDS
from phase55.config import FROZEN


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["timestamp_ct"])
    tz = ts.dt.tz
    return df.loc[(ts >= pd.Timestamp(start, tz=tz)) & (ts <= pd.Timestamp(end, tz=tz))]


def load_score_spec() -> dict:
    return json.loads((FROZEN / "phase53_score_spec.json").read_text())


def load_fold_models() -> list[dict]:
    out = []
    for p in sorted(FROZEN.glob("fold_*_model.joblib")):
        out.append(joblib.load(p))
    return out


def fold_for_timestamp(ts: pd.Timestamp, models: list[dict]) -> dict | None:
    ts = pd.Timestamp(ts)
    for m in models:
        tz = ts.tz
        if pd.Timestamp(m["test_start"], tz=tz) <= ts <= pd.Timestamp(m["test_end"], tz=tz):
            return m
    return None


def score_events(events: pd.DataFrame, models: list[dict] | None = None) -> pd.DataFrame:
    if events.empty:
        return events
    models = models or load_fold_models()
    out = events.copy()
    scores = np.full(len(out), np.nan)
    folds = np.full(len(out), np.nan)
    for k, row in out.iterrows():
        m = fold_for_timestamp(row["timestamp_ct"], models)
        if m is None:
            continue
        feats = m["features"]
        if any(f not in out.columns for f in feats):
            continue
        x = row[feats].astype(float).values.reshape(1, -1)
        if np.any(~np.isfinite(x)):
            continue
        xs = m["scaler"].transform(x)
        scores[out.index.get_loc(k)] = m["model"].predict_proba(xs)[0, 1]
        folds[out.index.get_loc(k)] = m["fold"]
    out["score"] = scores
    out["fold"] = folds
    return out


def apply_d10(events: pd.DataFrame, *, use_qcut: bool = True) -> pd.DataFrame:
    out = events.dropna(subset=["score"]).copy()
    if out.empty:
        return out
    if use_qcut:
        out["decile"] = pd.qcut(out["score"], 10, labels=False, duplicates="drop") + 1
        out["top10"] = out["decile"] == 10
        out["top20"] = out["score"] >= out["score"].quantile(0.8)
    else:
        spec = load_score_spec()
        thr = spec["d10_min_score_inclusive"]
        out["top10"] = out["score"] >= thr
        out["top20"] = out["score"] >= out["score"].quantile(0.8)
    return out


def score_events_batch_reference(events: pd.DataFrame) -> pd.DataFrame:
    """Use frozen walk_forward_models for parity reference path."""
    from phase53.research.features import feature_columns
    from phase53.research.models import walk_forward_models

    feats = feature_columns(events)
    stitched, _, _ = walk_forward_models(events, feats, target="opp_O2", max_features=8)
    return stitched
