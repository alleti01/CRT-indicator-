"""Phase 29 tests."""

from __future__ import annotations

from phase29.config import hold_bars, frozen_config_15m


def test_hold_bars_15m():
    assert hold_bars(60) == 4
    assert hold_bars(30) == 2
    assert hold_bars(180) == 12


def test_frozen_15m_config():
    cfg = frozen_config_15m()
    assert cfg.chart_minutes == 15
    assert cfg.trade_max_bars == 4
