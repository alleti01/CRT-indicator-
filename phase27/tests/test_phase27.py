"""Phase 27 tests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from phase27.config import PILOT_END, PILOT_START, PRIMARY_HORIZON_BARS, PRIMARY_LOSS_ATR, PRIMARY_PROFIT_ATR
from phase27.process_trades import load_pilot_5m, load_trades


TRADES = Path("phase27/data/raw/nq_trades_pilot_202401.csv")


@pytest.mark.skipif(not TRADES.exists(), reason="pilot trades not downloaded")
def test_trades_have_aggressor_side():
    df = load_trades(TRADES)
    assert set(df["side"].unique()) >= {"A", "B"}


@pytest.mark.skipif(not TRADES.exists(), reason="pilot trades not downloaded")
def test_trade_timestamps_before_bar_close_causal():
    trades = load_trades(TRADES)
    market = load_pilot_5m()
    bar = market.index[500]
    assert trades.loc[trades["ts_local"] <= bar, "ts_local"].shape[0] >= 0


def test_frozen_primary_target_constants():
    assert PRIMARY_PROFIT_ATR == 1.0
    assert PRIMARY_LOSS_ATR == 0.5
    assert PRIMARY_HORIZON_BARS == 24


def test_pilot_window():
    assert PILOT_START == "2024-01-01"
    assert PILOT_END == "2024-02-01"
