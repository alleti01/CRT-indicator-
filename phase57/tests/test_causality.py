"""Causality, lookahead, and S54 integrity tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57.research.fvg import detect_fvgs
from phase57.research.orb import detect_orb_ranges
from phase57.research.legs import detect_legs
from phase57.config import S54_MODEL_HASH, PHASE55_FROZEN


def _random_ohlc(n: int = 500) -> pd.DataFrame:
    np.random.seed(99)
    prices = np.cumsum(np.random.randn(n) * 0.5) + 100
    hi = prices + np.abs(np.random.randn(n)) * 0.8
    lo = prices - np.abs(np.random.randn(n)) * 0.8
    op = prices - 0.2
    cl = prices + 0.2
    idx = pd.date_range("2024-01-02 08:00", periods=n, freq="1min", tz="America/Chicago")
    df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": cl}, index=idx)
    df["atr"] = pd.Series(hi - lo).rolling(14, min_periods=1).mean().values
    return df


def test_fvg_no_lookahead():
    """Truncating future bars must not change detected FVGs."""
    m1 = _random_ohlc(500)
    full = detect_fvgs(m1)
    trunc = detect_fvgs(m1.iloc[:300])
    full_in_range = [f for f in full if f.formation_i < 300]
    assert len(full_in_range) == len(trunc)


def test_leg_no_future_pivots():
    m1 = _random_ohlc(500)
    full = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    trunc = detect_legs(m1.iloc[:300], start_i=20, min_distance_atr=0.5)
    full_in_range = [l for l in full if l.end_i < 300]
    for lt in trunc:
        match = [lf for lf in full_in_range if lf.start_i == lt.start_i and lf.end_i == lt.end_i]
        assert len(match) >= 1


def test_deterministic_rerun():
    """Same data → same results on repeated runs."""
    m1 = _random_ohlc(300)
    fvgs1 = detect_fvgs(m1)
    fvgs2 = detect_fvgs(m1)
    assert len(fvgs1) == len(fvgs2)
    for a, b in zip(fvgs1, fvgs2):
        assert a.formation_i == b.formation_i
        assert a.direction == b.direction


def test_s54_model_hash_unchanged():
    """S54 model hash must remain frozen."""
    h = (PHASE55_FROZEN / "model_hash.txt").read_text().strip()
    assert h == S54_MODEL_HASH, f"S54 model hash changed: {h} != {S54_MODEL_HASH}"


def test_timezone_consistency():
    m1 = _random_ohlc(200)
    assert str(m1.index.tz) == "America/Chicago"
    fvgs = detect_fvgs(m1)
    for f in fvgs:
        assert str(f.formation_ts.tz) == "America/Chicago"
