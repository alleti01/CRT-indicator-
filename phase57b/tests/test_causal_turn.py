"""Causal turn detection tests — no future information."""
from __future__ import annotations

import numpy as np
import pandas as pd
from phase57.research.legs import detect_legs
from phase57b.research.causal_turn import detect_causal_turns, TurnType


def _trending(n=300):
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 0.3 + 0.1) + 100
    hi = prices + np.abs(np.random.randn(n)) * 0.5
    lo = prices - np.abs(np.random.randn(n)) * 0.5
    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="1min", tz="America/Chicago")
    df = pd.DataFrame({"open": prices - 0.1, "high": hi, "low": lo, "close": prices + 0.1}, index=idx)
    df["atr"] = pd.Series(hi - lo).rolling(14, min_periods=1).mean().values
    return df


def test_turn_is_causal_no_future():
    """Turn entry_i must use only information available at that bar."""
    m1 = _trending(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    turns = detect_causal_turns(m1, legs)
    for t in turns:
        assert t.entry_i == t.turn_i
        assert t.turn_i > t.leg.end_i
        assert t.qualification_i <= t.turn_i
        assert t.qualification_i > t.leg.end_i


def test_truncation_invariance():
    """Turns detected on truncated data must match full-data turns."""
    m1 = _trending(400)
    legs_full = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    turns_full = detect_causal_turns(m1, legs_full)
    legs_trunc = detect_legs(m1.iloc[:250], start_i=20, min_distance_atr=0.5)
    turns_trunc = detect_causal_turns(m1.iloc[:250], legs_trunc)
    full_in_range = [t for t in turns_full if t.entry_i < 250 and t.leg.end_i < 250]
    for tt in turns_trunc:
        match = [tf for tf in full_in_range if tf.leg.leg_id == tt.leg.leg_id]
        if match:
            assert match[0].entry_i == tt.entry_i, f"Turn entry changed: {match[0].entry_i} vs {tt.entry_i}"


def test_turn_types_valid():
    m1 = _trending(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    turns = detect_causal_turns(m1, legs)
    for t in turns:
        assert t.turn_type in (TurnType.T1_CLOSE_REVERSAL, TurnType.T2_BODY_REVERSAL, TurnType.T3_WICK_REJECTION)
        assert t.direction in ("LONG", "SHORT")


def test_one_turn_per_leg():
    m1 = _trending(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    turns = detect_causal_turns(m1, legs)
    leg_ids = [t.leg.leg_id for t in turns]
    assert len(leg_ids) == len(set(leg_ids)), "Multiple turns for same leg"


def test_s54_hash_unchanged():
    from phase57b.config import PHASE55_FROZEN, S54_MODEL_HASH
    h = (PHASE55_FROZEN / "model_hash.txt").read_text().strip()
    assert h == S54_MODEL_HASH
