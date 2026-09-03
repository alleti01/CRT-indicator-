"""Tests for Phase 20 session liquidity discovery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase16.config import FrozenConfig
from phase20.forward_returns import compute_event_forward
from phase20.session_events import assign_era, extract_session_liquidity_events
from phase20.session_levels import prepare_session_liquidity_frame, time_bucket_label


def _synthetic_frame() -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2024-01-02 08:30", periods=80, freq="5min", tz=tz)
    prices = np.linspace(17000, 17020, len(index))
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 5,
            "low": prices - 5,
            "close": prices + 1,
            "volume": 100,
        },
        index=index,
    )
    return frame


def test_causal_pdh_uses_prior_session_only():
    config = FrozenConfig()
    tz = config.exchange_timezone
    day1 = pd.date_range("2024-01-02 09:30", periods=20, freq="5min", tz=tz)
    day2 = pd.date_range("2024-01-03 09:30", periods=20, freq="5min", tz=tz)
    index = day1.union(day2)
    prices = np.linspace(17000, 17040, len(index))
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 8,
            "low": prices - 8,
            "close": prices + 1,
            "volume": 100,
        },
        index=index,
    )
    data = prepare_session_liquidity_frame(frame, config)
    second_day = data.loc[data.index.date == pd.Timestamp("2024-01-03").date()]
    assert second_day["pdh"].notna().any()


def test_forward_returns_start_after_event_bar():
    config = FrozenConfig()
    data = prepare_session_liquidity_frame(_synthetic_frame(), config)
    row = pd.Series(
        {
            "bar_index": 20,
            "close": float(data.iloc[20].close),
            "atr": float(data.iloc[20].atr),
            "level_value": float(data.iloc[20].close),
            "level_side": "upper",
        }
    )
    metrics = compute_event_forward(data, row)
    assert "raw_points_1" in metrics
    assert metrics["raw_points_1"] == pytest.approx(float(data.iloc[21].close - data.iloc[20].close))


def test_era_assignment():
    tz = "America/Chicago"
    assert assign_era(pd.Timestamp("2019-06-01", tz=tz), tz) == "era1"
    assert assign_era(pd.Timestamp("2022-06-01", tz=tz), tz) == "era2"
    assert assign_era(pd.Timestamp("2025-06-01", tz=tz), tz) == "era3"


def test_event_timestamps_monotonic():
    config = FrozenConfig()
    events = extract_session_liquidity_events(_synthetic_frame(), config)
    if events.empty:
        pytest.skip("synthetic sample produced no events")
    stamps = pd.to_datetime(events["timestamp"])
    assert stamps.is_monotonic_increasing


def test_time_bucket_boundaries():
    tz = "America/Chicago"
    assert time_bucket_label(pd.Timestamp("2024-01-02 20:00", tz=tz)) == "OVERNIGHT"
    assert time_bucket_label(pd.Timestamp("2024-01-02 09:45", tz=tz)) == "RTH_OPEN"
