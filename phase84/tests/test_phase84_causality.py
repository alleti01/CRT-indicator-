"""Phase84 causality tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase84.python.config import EXPECTED_PINE_SHA256, pine_sha256
from phase84.python.features import compute_features_at_signal
from phase84.python.causality import truncation_test


def _synthetic_m1(n: int = 300) -> pd.DataFrame:
    np.random.seed(7)
    p = np.cumsum(np.random.randn(n)) + 20000
    idx = pd.date_range("2024-06-03 14:00", periods=n, freq="1min", tz="UTC")
    hi = p + np.abs(np.random.randn(n))
    lo = p - np.abs(np.random.randn(n))
    df = pd.DataFrame({"open": p, "high": hi, "low": lo, "close": p + 0.1}, index=idx)
    df["atr"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
    return df


def test_pine_hash_frozen():
    assert pine_sha256() == EXPECTED_PINE_SHA256


def test_truncation_invariance_features():
    m1 = _synthetic_m1()
    hi = m1["high"].values
    lo = m1["low"].values
    cl = m1["close"].values
    op = m1["open"].values
    atr = m1["atr"].values
    i = 100
    full = compute_features_at_signal(hi, lo, cl, op, atr, i, "LONG")
    part = compute_features_at_signal(hi[: i + 1], lo[: i + 1], cl[: i + 1], op[: i + 1], atr[: i + 1], i, "LONG")
    assert full["range_position_20"] == part["range_position_20"]
    assert full["failed_break"] == part["failed_break"]


def test_truncation_runner():
    m1 = _synthetic_m1()
    sig = pd.DataFrame({
        "phase72a_event_id": ["t1"],
        "phase72a_signal_time": [m1.index[100]],
        "phase72a_direction": ["LONG"],
        "phase72a_source": ["TEST"],
        "signal_i": [100],
        "entry_i": [101],
    })
    r = truncation_test(m1, sig, sample=1, variant="E3")
    assert r["pass"] is True
