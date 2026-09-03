"""Phase 28 tests."""

from __future__ import annotations

import pandas as pd
import pytest

from phase16.config import FrozenConfig
from phase28.config import config_for_timeframe
from phase28.resample_timeframes import aggregate_from_5m


def _sample_5m() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=24, freq="5min", tz="America/Chicago")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 100,
        },
        index=idx,
    )


def test_aggregate_15m_no_lookahead():
    base = _sample_5m()
    out = aggregate_from_5m(base, 15)
    assert len(out) == 8
    assert out.index[0] == base.index[0]


def test_time_based_max_hold_scales():
    assert config_for_timeframe(5).trade_max_bars == 12
    assert config_for_timeframe(15).trade_max_bars == 4
    assert config_for_timeframe(30).trade_max_bars == 2
    assert config_for_timeframe(60).trade_max_bars == 1


def test_structural_bar_counts_unchanged():
    base = FrozenConfig()
    cfg60 = config_for_timeframe(60)
    assert cfg60.p12_expiry_bars == base.p12_expiry_bars
    assert cfg60.se_cooldown_bars == base.se_cooldown_bars
