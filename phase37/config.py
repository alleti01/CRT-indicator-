"""Phase 37 concurrent reversal parity configuration."""

from __future__ import annotations

from pathlib import Path

from phase29.config import ROUND_TURN_COST_USD, hold_bars
from phase36.config import REPLAY_END, REPLAY_START

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase37" / "results" / "concurrent_reversal_parity"

# Frozen Phase 33 reversal (unchanged)
P33_FAILURE_DEF = "A_MID_4"
P33_FAILURE_WIN = 4
P33_RETEST_WIN = 2
P33_STOP_ATR = 0.75
P33_TARGET_R = 2.5
P33_MAX_HOLD_BARS = hold_bars(45)

# Dedupe — matches phase31.dedupe defaults used by phase34 build_p33_reference
DEDUPE_ACTIVE_BARS = 6
DEDUPE_SAME_DIR = 4
DEDUPE_DAY_CAP = 2
DEDUPE_MAX_HOLD_BARS = 4

# Phase 36 single-tracker reference
P36_SIGNAL_MAP = ROOT / "phase36" / "results" / "full_history_signal_replay" / "full_history_signal_map.csv"
