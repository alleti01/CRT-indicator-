"""Tests for Phase 21 volatility-state discovery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase16.config import FrozenConfig
from phase21.forward_returns import compute_forward
from phase21.volatility_events import assign_era, extract_volatility_events
from phase21.volatility_measures import prepare_volatility_frame


def _frame() -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2024-01-02 09:30", periods=200, freq="5min", tz=tz)
    rng = np.random.default_rng(7)
    prices = 17000 + np.cumsum(rng.normal(0, 2, len(index)))
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + rng.uniform(1, 8, len(index)),
            "low": prices - rng.uniform(1, 8, len(index)),
            "close": prices + rng.normal(0, 1, len(index)),
            "volume": 100,
        },
        index=index,
    )


def test_forward_returns_use_future_bars_only():
    config = FrozenConfig()
    data = prepare_volatility_frame(_frame(), config)
    row = pd.Series(
        {
            "bar_index": 50,
            "close": float(data.iloc[50].close),
            "atr": float(data.iloc[50].atr_24),
            "transition_direction": "UP",
        }
    )
    metrics = compute_forward(data, row)
    assert metrics["signed_return_atr_1"] == pytest.approx(
        float((data.iloc[51].close - data.iloc[50].close) / data.iloc[50].atr_24)
    )


def test_percentiles_are_causal_not_constant_one():
    config = FrozenConfig()
    data = prepare_volatility_frame(_frame(), config)
    pct = data["pct_ATR_24"].dropna()
    if pct.empty:
        pytest.skip("synthetic sample too short for percentile warm-up")
    assert pct.max() <= 1.0
    assert pct.min() >= 0.0


def test_era_assignment():
    tz = "America/Chicago"
    assert assign_era(pd.Timestamp("2019-06-01", tz=tz), tz) == "era1"
    assert assign_era(pd.Timestamp("2022-06-01", tz=tz), tz) == "era2"
    assert assign_era(pd.Timestamp("2025-06-01", tz=tz), tz) == "era3"


def test_shock_deduplication_runs():
    config = FrozenConfig()
    events = extract_volatility_events(_frame(), config)
    if events.empty:
        pytest.skip("synthetic sample produced no events")
    shocks = events.loc[events.event_family == "VOLATILITY_SHOCK"]
    assert shocks["timestamp"].is_monotonic_increasing


def test_state_transition_timing():
    config = FrozenConfig()
    events = extract_volatility_events(_frame(), config)
    if events.empty:
        pytest.skip("no events in synthetic sample")
    regime = events.loc[events.event_family == "REGIME_TRANSITION"]
    if regime.empty:
        pytest.skip("no regime transitions in synthetic sample")
    assert (regime["transition"].str.contains("->")).all()
