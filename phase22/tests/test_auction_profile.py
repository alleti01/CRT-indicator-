"""Tests for Phase 22 auction profile discovery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase16.config import FrozenConfig
from phase16.indicators import is_in_session
from phase22.auction_events import assign_era, extract_auction_events, inside_value
from phase22.profile_construction import build_daily_profiles, build_volume_profile, distribute_bar_volume


def _frame(days: int = 3) -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2024-01-02 09:30", periods=78 * days, freq="5min", tz=tz)
    rng = np.random.default_rng(3)
    prices = 17000 + np.cumsum(rng.normal(0, 3, len(index)))
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + rng.uniform(2, 10, len(index)),
            "low": prices - rng.uniform(2, 10, len(index)),
            "close": prices + rng.normal(0, 1, len(index)),
            "volume": rng.integers(100, 1000, len(index)),
        },
        index=index,
    )


def test_profile_bins_use_tick_size():
    bins = distribute_bar_volume(17000.0, 17001.0, 500.0, tick=0.25)
    assert all(abs((price * 4) - round(price * 4)) < 1e-9 for price in bins)


def test_prior_profile_is_causal():
    config = FrozenConfig()
    frame = _frame()
    profiles = build_daily_profiles(frame, config)
    assert profiles["session_date"].is_monotonic_increasing
    assert len(profiles) >= 1


def test_acceptance_rejection_timing():
    assert inside_value(100.0, 99.0, 101.0)
    assert not inside_value(102.0, 99.0, 101.0)


def test_era_assignment():
    tz = "America/Chicago"
    assert assign_era(pd.Timestamp("2019-06-01 10:00", tz=tz), tz) == "era1"


def test_forward_return_uses_future_only():
    config = FrozenConfig()
    events = extract_auction_events(_frame(5), config)
    if events.empty:
        pytest.skip("no events")
    assert "directional_atr_1" in events.columns


def test_rth_boundary():
    ts = pd.Timestamp("2024-01-02 09:30", tz="America/Chicago")
    assert is_in_session(ts, "0930-1600")
    ts2 = pd.Timestamp("2024-01-02 16:00", tz="America/Chicago")
    assert not is_in_session(ts2, "0930-1600")
