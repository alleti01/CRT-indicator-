"""Frozen Phase 32 Momentum Displacement constants."""

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
RESULTS = ROOT / "phase32" / "results" / "pine_implementation"

SIGNAL_ARCHITECTURE = "MOMENTUM_DISPLACEMENT"
TIMEFRAME_MINUTES = 15

# Displacement trigger (frozen)
BODY_AVG_LOOKBACK = 20
BODY_MULTIPLIER = 1.5
CLOSE_LOC_LONG_MIN = 0.80
CLOSE_LOC_SHORT_MAX = 0.20
RTH_SESSION = "0930-1600"

# BOS_RETEST (phase29.simulator.resolve_entry — literal)
ENTRY_MODEL = "BOS_RETEST"
# BOS level = displacement bar high (long) or low (short)
# Tolerance ATR = displacement bar ATR × 0.10
# Window = 2 bars strictly after displacement bar closes
# Long: low <= bos_level + tol; fill min(bos_level + tol, close)
# Short: high >= bos_level - tol; fill max(bos_level - tol, close)

# Execution (frozen WF mode)
STOP_ATR = 0.75
TARGET_R = 3.0
MAX_HOLD_MINUTES = 60
MAX_HOLD_BARS = hold_bars(MAX_HOLD_MINUTES)
MANAGEMENT = "FIXED"
ATR_LENGTH = 14

# Dedupe (phase31.dedupe)
MIN_BARS_BETWEEN_SAME_DIR = 4
ONE_ACTIVE_TRADE = True
DEDUPE_ACTIVE_BARS = 6
MAX_SIGNALS_PER_RTH_DAY = 2

AMBIGUOUS_BAR_POLICY = (
    "If stop and target are both touched within the same 15m bar, STOP is evaluated "
    "before TARGET (conservative). Matches phase29.simulator.simulate_trade."
)

# Phase 31 reference populations (do not conflate)
PHASE31_STITCHED_WF = {
    "N": 2873,
    "rth_days": 2188,
    "trades_per_day": 1.222,
    "net_AvgR": 0.233,
    "net_TotalR": 670.3,
    "net_PF": 1.47,
}

PHASE31_DRY_STRETCH_REPORTED = 515
