"""Phase 36 full-history replay configuration."""

from __future__ import annotations

from pathlib import Path

from phase29.config import (
    BOS_RETEST_TOLERANCE_ATR,
    NQ_5M_PATHS,
    RETRACE_WINDOW_BARS,
    ROUND_TURN_COST_USD,
    hold_bars,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase36" / "results" / "full_history_signal_replay"

# Target historical range (use max available after bar construction)
REPLAY_START = "2017-10-01"
REPLAY_END = "2026-06-28"

RTH_SESSION = "0930-1600"
CHART_MINUTES = 15

# Frozen Phase 31 continuation
P31_BODY_AVG_LEN = 20
P31_BODY_MULT = 1.5
P31_CL_LONG = 0.80
P31_CL_SHORT = 0.20
P31_STOP_ATR = 0.75
P31_TARGET_R = 3.0
P31_MAX_HOLD_BARS = hold_bars(60)
P31_BOS_RETEST_WIN = RETRACE_WINDOW_BARS

# Frozen Phase 33 reversal
P33_FAILURE_WIN = 4
P33_RETEST_WIN = RETRACE_WINDOW_BARS
P33_STOP_ATR = 0.75
P33_TARGET_R = 2.5
P33_MAX_HOLD_BARS = hold_bars(45)

# Shared dedupe (matches Pine / Phase 34)
DEDUPE_ACTIVE_BARS = 6
DEDUPE_SAME_DIR = 4
DEDUPE_DAY_CAP = 2

BOS_RETEST_TOL_ATR = BOS_RETEST_TOLERANCE_ATR

# Phase 34 parity reference for Pine-equivalent comparison
P34_COMBINED_REFERENCE = ROOT / "phase34" / "results" / "combined_pine" / "combined_parity_reference.csv"
