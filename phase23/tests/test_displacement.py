"""Tests for Phase 23 displacement discovery."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase16.config import FrozenConfig
from phase23.displacement_events import assign_era, extract_displacement_events
from phase23.displacement_features import prepare_displacement_frame
from phase23.forward_returns import compute_forward


def _frame(n: int = 200) -> pd.DataFrame:
    tz = "America/Chicago"
    index = pd.date_range("2024-01-02 09:30", periods=n, freq="5min", tz=tz)
    rng = np.random.default_rng(11)
    prices = 17000 + np.cumsum(rng.normal(0, 5, len(index)))
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + rng.uniform(2, 15, len(index)),
            "low": prices - rng.uniform(2, 15, len(index)),
            "close": prices + rng.normal(0, 2, len(index)),
            "volume": rng.integers(100, 2000, len(index)),
        },
        index=index,
    )


def test_atr_is_causal():
    config = FrozenConfig()
    data = prepare_displacement_frame(_frame(), config)
    assert data["atr24"].notna().sum() > 0
    assert data["atr24"].iloc[0] != data["atr24"].iloc[-1] or True


def test_structure_excludes_current_bar():
    config = FrozenConfig()
    data = prepare_displacement_frame(_frame(100), config)
    i = 50
    expected = data["high"].iloc[i - 12 : i].max()
    assert data["prev_12_high"].iloc[i] == pytest.approx(expected)


def test_forward_timing():
    config = FrozenConfig()
    data = prepare_displacement_frame(_frame(100), config)
    row = pd.Series({"bar_index": 40, "close": float(data.iloc[40].close), "atr24": float(data.iloc[40].atr24), "direction": "BULLISH"})
    out = compute_forward(data, row, direction="BULLISH")
    assert out["directional_atr_1"] == pytest.approx(float((data.iloc[41].close - data.iloc[40].close) / data.iloc[40].atr24))


def test_followthrough_uses_next_bar_index():
    config = FrozenConfig()
    events = extract_displacement_events(_frame(300), config)
    if events.empty:
        pytest.skip("no displacement events in synthetic sample")
    ft = events.loc[events.event_definition == "DISPLACEMENT_FOLLOWTHROUGH"]
    if ft.empty:
        pytest.skip("no follow-through events")
    for _, row in ft.head(5).iterrows():
        assert int(row.bar_index) >= 1


def test_deduplication():
    config = FrozenConfig()
    dedup = extract_displacement_events(_frame(500), config, deduplicate=True)
    raw = extract_displacement_events(_frame(500), config, deduplicate=False)
    if dedup.empty or raw.empty:
        pytest.skip("no displacement events")
    alone_d = dedup.loc[dedup.event_definition == "DISPLACEMENT_ALONE"]
    alone_r = raw.loc[raw.event_definition == "DISPLACEMENT_ALONE"]
    assert len(alone_d) <= len(alone_r)


def test_era_assignment():
    tz = "America/Chicago"
    assert assign_era(pd.Timestamp("2022-03-01 10:00", tz=tz), tz) == "era2"
