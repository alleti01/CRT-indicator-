"""Forward scoring with frozen fold-5 model and D10 threshold."""

from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from phase55.config import FROZEN
from phase56.config import FORWARD_SCORING_FOLD


def load_score_spec() -> dict:
    return json.loads((FROZEN / "phase53_score_spec.json").read_text())


def load_forward_model() -> dict:
    """Frozen fold model for forward timestamps (post-holdout)."""
    path = FROZEN / f"fold_{FORWARD_SCORING_FOLD}_model.joblib"
    return joblib.load(path)


def score_event_row(row: pd.Series, model_blob: dict) -> float | None:
    feats = model_blob["features"]
    if any(f not in row.index for f in feats):
        return None
    x = row[feats].astype(float).values.reshape(1, -1)
    if np.any(~np.isfinite(x)):
        return None
    xs = model_blob["scaler"].transform(x)
    return float(model_blob["model"].predict_proba(xs)[0, 1])


def d10_pass(score: float | None, spec: dict | None = None) -> bool:
    if score is None or not np.isfinite(score):
        return False
    spec = spec or load_score_spec()
    return float(score) >= float(spec["d10_min_score_inclusive"])
