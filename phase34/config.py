"""Phase 34 combined Pine configuration."""

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
    NQ_DOLLARS_PER_POINT,
    hold_bars,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase34" / "results" / "combined_pine"

# Phase 31 continuation (frozen)
P31_ARCH = "MOMENTUM_DISPLACEMENT"
P31_ENTRY = "BOS_RETEST"
P31_STOP_ATR = 0.75
P31_TARGET_R = 3.0
P31_HOLD_MINUTES = 60
P31_MAX_HOLD_BARS = hold_bars(P31_HOLD_MINUTES)

# Phase 33 reversal (frozen WF selection)
P33_ARCH = "DISPLACEMENT_FAILURE_REVERSAL"
P33_FAILURE_DEF = "A_MID_4"
P33_ENTRY = "RECLAIM_RETEST"
P33_FAILURE_WINDOW = 4
P33_STOP_ATR = 0.75
P33_TARGET_R = 2.5
P33_HOLD_MINUTES = 45
P33_MAX_HOLD_BARS = hold_bars(P33_HOLD_MINUTES)

# Shared displacement + session
BODY_AVG_LOOKBACK = 20
BODY_MULTIPLIER = 1.5
CLOSE_LOC_LONG_MIN = 0.80
CLOSE_LOC_SHORT_MAX = 0.20
RTH_SESSION = "0930-1600"
ATR_LENGTH = 14
BOS_RETEST_WIN = 2
DEDUPE_ACTIVE_BARS = 6
DEDUPE_SAME_DIR = 4
DEDUPE_DAY_CAP = 2

# Research benchmarks (validation only)
P31_WF_BENCHMARK = {"N": 2873, "trades_day": 1.22, "AvgR": 0.233, "PF": 1.47, "MaxDD": 15.1}
P33_WF_BENCHMARK = {"N": 1031, "trades_day": 0.44, "AvgR": 0.185, "PF": 1.46, "MaxDD": 21.2}
COMBINED_BENCHMARK = {"trades_day": 1.78, "AvgR": 0.220, "PF": 1.47, "MaxDD": 16.8}

CONFLICT_POLICY = "INDEPENDENT"
