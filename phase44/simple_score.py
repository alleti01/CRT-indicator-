"""Phase 43 simple-score causal proxy for Pine parity."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Q_PASS_MIN, Q_RAW_HI, Q_RAW_LO, Q_TIER_A, Q_TIER_APLUS, Q_TIER_B


def ret_n_atr(close_now: float, close_n: float, direction: int) -> float:
    if close_n == 0:
        return 0.0
    return ((close_now / close_n) - 1.0) * direction


def simple_raw(ret_1_atr: float, ret_2_atr: float, ret_3_atr: float) -> float:
    return float(ret_1_atr + ret_2_atr + ret_3_atr)


def quality_score(raw: float) -> float:
    span = Q_RAW_HI - Q_RAW_LO
    if span <= 0:
        return 50.0
    return float(np.clip((raw - Q_RAW_LO) / span * 100.0, 0.0, 100.0))


def quality_pass(score: float) -> bool:
    return score >= Q_PASS_MIN


def confidence_tier(score: float, *, accepted: bool) -> str:
    if not accepted:
        return "C"
    if score >= Q_TIER_APLUS:
        return "A+"
    if score >= Q_TIER_A:
        return "A"
    if score >= Q_TIER_B:
        return "B"
    return "C"


def score_from_features(row: pd.Series) -> tuple[float, float, bool, str]:
    r1 = float(row["ret_1_atr"])
    r2 = float(row["ret_2_atr"])
    r3 = float(row["ret_3_atr"])
    raw = simple_raw(r1, r2, r3)
    sc = quality_score(raw)
    acc = quality_pass(sc)
    tier = confidence_tier(sc, accepted=acc)
    return raw, sc, acc, tier
