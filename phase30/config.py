"""Frozen Phase 30 Pine implementation constants."""

from __future__ import annotations

from pathlib import Path

from phase29.config import (
    BOS_RETEST_TOLERANCE_ATR,
    CHART_MINUTES,
    COMMON_END,
    COMMON_START,
    ERAS,
    RETRACE_WINDOW_BARS,
    ROUND_TURN_COST_USD,
    VARIANT_ID,
    frozen_config_15m,
    hold_bars,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase30" / "results" / "pine_implementation"

SIGNAL_ARCHITECTURE = "CRT_V2_B_LEGACY_EXP6"
ENTRY_MODEL = "BOS_RETEST"
STOP_ATR = 0.75
TARGET_R = 3.0
MAX_HOLD_MINUTES = 60
MAX_HOLD_BARS = hold_bars(MAX_HOLD_MINUTES)
MANAGEMENT = "FIXED"
SETUP_BOS_EXPIRY_BARS = 6

AMBIGUOUS_BAR_POLICY = (
    "If stop and target are both touched within the same bar and intrabar order is unknown, "
    "STOP is assumed first (conservative). Matches phase16.trade_engine.manage_bar and "
    "phase29.simulator.simulate_trade."
)

BASELINE_15M = {
    "N": 210,
    "net_AvgR": 0.094,
    "net_PF": 1.31,
}

WF_EXECUTION = {
    "N": 110,
    "net_AvgR": 0.325,
    "net_TotalR": 35.8,
    "net_PF": 1.89,
    "MaxDD": 5.1,
}
