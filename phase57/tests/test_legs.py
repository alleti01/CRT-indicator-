"""Leg/pullback/retest causality tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57.research.legs import detect_legs, PriceLeg
from phase57.research.pullbacks import detect_pullbacks
from phase57.research.retests import Retest


def _trending_up(n: int = 200) -> pd.DataFrame:
    """Generate an uptrending 1M series with swings."""
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 0.3 + 0.1) + 100
    hi = prices + np.abs(np.random.randn(n)) * 0.5
    lo = prices - np.abs(np.random.randn(n)) * 0.5
    op = prices - 0.1
    cl = prices + 0.1
    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="1min", tz="America/Chicago")
    df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": cl}, index=idx)
    df["atr"] = pd.Series(hi - lo).rolling(14, min_periods=1).mean().values
    return df


def test_leg_detection_causal():
    """Legs must use only past data — truncating must not change earlier legs."""
    m1 = _trending_up(300)
    legs_full = detect_legs(m1, start_i=20)
    legs_trunc = detect_legs(m1.iloc[:200], start_i=20)
    # Every leg detected in truncated must exist identically in full
    for lt in legs_trunc:
        match = [lf for lf in legs_full if lf.start_i == lt.start_i and lf.end_i == lt.end_i]
        assert len(match) >= 1, f"Leg at {lt.start_i}-{lt.end_i} missing in full run"


def test_leg_has_required_fields():
    m1 = _trending_up(200)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    if legs:
        leg = legs[0]
        assert leg.direction in ("BULL", "BEAR")
        assert leg.distance_atr >= 0.5
        assert leg.duration >= 0
        assert 0 <= leg.efficiency <= 1.5
        assert leg.leg_id.startswith("LEG-")


def test_pullback_depth_pct():
    m1 = _trending_up(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    pbs = detect_pullbacks(m1, legs, min_depth_pct=0.1)
    for pb in pbs:
        assert 0.1 <= pb.depth_pct_of_leg <= 1.0
        assert pb.duration > 0


def test_pullback_no_future_pivots():
    """Pullback detection on truncated data must match."""
    m1 = _trending_up(300)
    legs = detect_legs(m1.iloc[:200], start_i=20, min_distance_atr=0.5)
    pbs_trunc = detect_pullbacks(m1.iloc[:200], legs)
    pbs_full = detect_pullbacks(m1, legs)
    # Same legs → should get same pullbacks (legs end before bar 200)
    for pt in pbs_trunc:
        match = [pf for pf in pbs_full if pf.leg.leg_id == pt.leg.leg_id]
        assert len(match) >= 1
