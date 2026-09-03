"""Retest detection tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57.research.fvg import FVG, detect_fvgs
from phase57.research.retests import detect_fvg_retests, Retest


def _make_ohlc(bars, start="2024-01-02 09:00"):
    idx = pd.date_range(start, periods=len(bars), freq="1min", tz="America/Chicago")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["atr"] = 10.0
    return df


def test_fvg_retest_detected():
    bars = [
        (100, 105, 98, 103),
        (104, 120, 103, 118),
        (119, 125, 108, 122),  # bullish FVG: lower=105, upper=108
        (122, 126, 120, 124),
        (124, 125, 107, 108),  # retest: lo=107 touches FVG upper=108
        (109, 115, 108, 113),
    ]
    df = _make_ohlc(bars)
    fvgs = detect_fvgs(df)
    retests = detect_fvg_retests(df, fvgs)
    assert len(retests) >= 1
    rt = retests[0]
    assert rt.retest_type == "T3"
    assert rt.direction == "LONG"


def test_fvg_retest_not_on_formation_bar():
    bars = [
        (100, 105, 98, 103),
        (104, 120, 103, 118),
        (119, 125, 108, 122),
    ]
    df = _make_ohlc(bars)
    fvgs = detect_fvgs(df)
    retests = detect_fvg_retests(df, fvgs)
    for rt in retests:
        assert rt.bar_i > fvgs[0].formation_i
