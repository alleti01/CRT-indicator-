"""ORB causality and detection tests."""

from __future__ import annotations

import pandas as pd
import pytest

from phase57.research.orb import detect_orb_ranges, classify_orb_events, ORBRange


def _make_session(bars: list[tuple], start: str = "2024-01-03 08:28") -> pd.DataFrame:
    """Build 1M OHLC starting at given CT time."""
    idx = pd.date_range(start, periods=len(bars), freq="1min", tz="America/Chicago")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["atr"] = 10.0
    return df


def test_orb5_not_actionable_before_window_closes():
    # 08:28, 08:29, 08:30, 08:31, 08:32, 08:33, 08:34, 08:35
    bars = [
        (100, 102, 99, 101),   # 08:28 — pre-open
        (101, 103, 100, 102),  # 08:29 — pre-open
        (102, 108, 101, 107),  # 08:30 — in ORB5
        (107, 110, 105, 109),  # 08:31
        (109, 112, 107, 111),  # 08:32
        (111, 115, 109, 113),  # 08:33
        (113, 116, 111, 114),  # 08:34
        (114, 118, 112, 116),  # 08:35 — first bar AFTER ORB5 closes
    ]
    df = _make_session(bars)
    ranges = detect_orb_ranges(df, window_min=5)
    assert len(ranges) == 1
    r = ranges[0]
    assert r.actionable_ts.time().hour == 8
    assert r.actionable_ts.time().minute == 35
    assert r.actionable_i == 7  # index of 08:35 bar


def test_orb_range_correct():
    bars = [
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 108, 98, 107),   # 08:30: h=108, l=98
        (107, 110, 105, 109),  # 08:31: h=110
        (109, 112, 107, 111),  # 08:32
        (111, 115, 109, 113),  # 08:33
        (113, 116, 111, 114),  # 08:34
        (114, 118, 112, 116),  # 08:35
    ]
    df = _make_session(bars)
    ranges = detect_orb_ranges(df, window_min=5)
    r = ranges[0]
    assert r.or_high == 116.0   # max of 08:30-08:34 (bar at 08:34 has high=116)
    assert r.or_low == 98.0     # min of 08:30-08:34


def test_orb_breakout_detected():
    bars = [
        (100, 102, 99, 101),
        (101, 103, 100, 102),
        (102, 105, 100, 104),  # 08:30
        (104, 106, 102, 105),  # 08:31
        (105, 107, 103, 106),  # 08:32
        (106, 108, 104, 107),  # 08:33
        (107, 109, 105, 108),  # 08:34
        (108, 115, 107, 113),  # 08:35 — breakout above or_high=109
    ]
    df = _make_session(bars)
    ranges = detect_orb_ranges(df, window_min=5)
    events = classify_orb_events(ranges[0], df)
    types = [e.event_type for e in events]
    assert "O1" in types


def test_orb_timezone_ct():
    """ORB detection must use America/Chicago timezone."""
    bars = [(100 + i, 105 + i, 98 + i, 103 + i) for i in range(20)]
    idx = pd.date_range("2024-01-03 08:25", periods=20, freq="1min", tz="America/Chicago")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["atr"] = 10.0
    ranges = detect_orb_ranges(df, window_min=5)
    if ranges:
        assert str(ranges[0].actionable_ts.tz) == "America/Chicago"
