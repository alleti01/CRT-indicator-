"""FVG causality and detection tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase57.research.fvg import FVG, classify_interaction, detect_fvgs


def _make_ohlc(bars: list[tuple]) -> pd.DataFrame:
    """Build a minimal OHLC DataFrame from (open, high, low, close) tuples."""
    idx = pd.date_range("2024-01-02 09:00", periods=len(bars), freq="1min", tz="America/Chicago")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["atr"] = 10.0
    return df


def test_bullish_fvg_detected():
    bars = [
        (100, 105, 98, 103),   # candle 1: high=105
        (104, 120, 103, 118),  # candle 2: impulse up
        (119, 125, 108, 122),  # candle 3: low=108 > candle1 high=105 → bullish FVG
    ]
    df = _make_ohlc(bars)
    fvgs = detect_fvgs(df, start_i=2)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == "BULL"
    assert f.lower == 105.0
    assert f.upper == 108.0
    assert f.formation_i == 2


def test_bearish_fvg_detected():
    bars = [
        (120, 125, 115, 118),  # candle 1: low=115
        (117, 118, 100, 102),  # candle 2: impulse down
        (101, 112, 98, 105),   # candle 3: high=112 < candle1 low=115 → bearish FVG
    ]
    df = _make_ohlc(bars)
    fvgs = detect_fvgs(df, start_i=2)
    assert len(fvgs) == 1
    f = fvgs[0]
    assert f.direction == "BEAR"
    assert f.upper == 115.0
    assert f.lower == 112.0


def test_no_fvg_when_gap_absent():
    bars = [
        (100, 110, 98, 108),
        (108, 115, 105, 112),
        (112, 118, 109, 116),  # low=109 < candle1 high=110 → overlap, no gap
    ]
    df = _make_ohlc(bars)
    assert len(detect_fvgs(df, start_i=2)) == 0


def test_fvg_only_after_bar3_closes():
    """FVG at bar index 2 means candle 3 is fully closed at that index."""
    bars = [
        (100, 105, 98, 103),
        (104, 120, 103, 118),
        (119, 125, 108, 122),
    ]
    df = _make_ohlc(bars)
    fvgs = detect_fvgs(df, start_i=2)
    assert all(f.formation_i >= 2 for f in fvgs)
    # Truncating to 2 bars must produce no FVG
    assert len(detect_fvgs(df.iloc[:2], start_i=2)) == 0


def test_fvg_truncation_invariance():
    """Adding future bars must not change FVGs detected up to a given bar."""
    bars = [
        (100, 105, 98, 103),
        (104, 120, 103, 118),
        (119, 125, 108, 122),
        (122, 130, 120, 128),
        (128, 135, 126, 133),
    ]
    df_full = _make_ohlc(bars)
    df_trunc = _make_ohlc(bars[:3])
    fvgs_full = [f for f in detect_fvgs(df_full) if f.formation_i <= 2]
    fvgs_trunc = detect_fvgs(df_trunc)
    assert len(fvgs_full) == len(fvgs_trunc)
    for a, b in zip(fvgs_full, fvgs_trunc):
        assert a.direction == b.direction
        assert a.upper == b.upper
        assert a.lower == b.lower


def test_interaction_classification():
    fvg = FVG(
        direction="BULL", formation_i=5, formation_ts=pd.Timestamp.now(),
        upper=110.0, lower=105.0, midpoint=107.5, size_pts=5.0, size_atr=0.5,
        impulse_body=8.0, impulse_body_atr=0.8, timeframe="1M",
    )
    # No interaction: bar entirely above FVG
    assert classify_interaction(fvg, 115.0, 111.0) is None
    # Edge touch: bar low barely enters
    assert classify_interaction(fvg, 115.0, 109.6) == "F1"
    # Partial penetration
    assert classify_interaction(fvg, 115.0, 108.5) == "F2"
    # Midpoint
    assert classify_interaction(fvg, 115.0, 107.5) == "F3"
    # Deep
    assert classify_interaction(fvg, 115.0, 105.8) == "F4"
    # Full fill
    assert classify_interaction(fvg, 115.0, 105.3) == "F5"
    # Trade through
    assert classify_interaction(fvg, 115.0, 104.0) == "F8"
