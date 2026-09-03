"""Frozen Phase 44 quality score — no recalibration permitted."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Q_PASS_MIN, Q_RAW_HI, Q_RAW_LO, Q_TIER_A, Q_TIER_APLUS, Q_TIER_B


def direction_code(direction: str) -> int:
    return 1 if str(direction).lower() == "long" else -1


def ret_n(close_now: float, close_n: float, direction: int) -> float:
    if close_n == 0 or not np.isfinite(close_n):
        return 0.0
    return ((close_now / close_n) - 1.0) * direction


def compute_returns(close: float, close_1: float, close_2: float, close_3: float, direction: int) -> tuple[float, float, float, float]:
    r1 = ret_n(close, close_1, direction)
    r2 = ret_n(close, close_2, direction)
    r3 = ret_n(close, close_3, direction)
    return r1, r2, r3, r1 + r2 + r3


def quality_score(simple_raw: float) -> float:
    span = Q_RAW_HI - Q_RAW_LO
    if span <= 0:
        return 50.0
    return float(np.clip((simple_raw - Q_RAW_LO) / span * 100.0, 0.0, 100.0))


def confidence_tier(score: float, *, quality_pass: bool) -> str:
    if not quality_pass:
        return "REJECTED"
    if score >= Q_TIER_APLUS:
        return "A+"
    if score >= Q_TIER_A:
        return "A"
    if score >= Q_TIER_B:
        return "B"
    return "REJECTED"


def evaluate_quality(close: float, close_1: float, close_2: float, close_3: float, direction: str) -> dict:
    d = direction_code(direction)
    r1, r2, r3, raw = compute_returns(close, close_1, close_2, close_3, d)
    score = quality_score(raw)
    qpass = score >= Q_PASS_MIN
    tier = confidence_tier(score, quality_pass=qpass)
    return {
        "ret_1": r1,
        "ret_2": r2,
        "ret_3": r3,
        "simple_raw": raw,
        "quality_score": score,
        "quality_filter_pass": qpass,
        "confidence_tier": tier,
    }


def pine_quality_raw(close: float, c1: float, c2: float, c3: float, direction: int) -> float:
    """Simulate Pine qualityRaw() for parity checks."""
    r1 = ((close - c1) / c1 * direction) if c1 else 0.0
    r2 = ((close - c2) / c2 * direction) if c2 else 0.0
    r3 = ((close - c3) / c3 * direction) if c3 else 0.0
    return r1 + r2 + r3


def assert_frozen_constants_unchanged() -> bool:
    """Verify constants match Phase 44 config exactly."""
    from phase44.config import Q_PASS_MIN as p44_pass
    from phase44.config import Q_RAW_HI as p44_hi
    from phase44.config import Q_RAW_LO as p44_lo
    from phase44.config import Q_TIER_A as p44_a
    from phase44.config import Q_TIER_APLUS as p44_ap
    from phase44.config import Q_TIER_B as p44_b

    return (
        abs(Q_RAW_LO - p44_lo) < 1e-6
        and abs(Q_PASS_MIN - p44_pass) < 1e-3
        and abs(Q_TIER_APLUS - p44_ap) < 1e-3
        and abs(Q_TIER_A - p44_a) < 1e-3
        and abs(Q_TIER_B - p44_b) < 1e-3
    )
