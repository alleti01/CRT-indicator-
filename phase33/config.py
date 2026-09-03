"""Phase 33 — displacement failure / reversal discovery."""

from __future__ import annotations

from pathlib import Path

from phase29.config import (
    COMMON_END,
    COMMON_START,
    NQ_5M_PATHS,
    ROUND_TURN_COST_USD,
    WALK_FORWARD_FOLDS,
)
from phase31.config import (
    CHART_MINUTES,
    MC_SIMULATIONS,
    NQ_DOLLARS_PER_POINT,
    RTH_SESSION,
    hold_bars,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase33" / "results" / "displacement_failure_reversal"
PHASE31_WF_TRADES = ROOT / "phase31" / "results" / "daily_frequency_entry" / "walk_forward_trades.csv"

ARCHITECTURE = "DISPLACEMENT_FAILURE_REVERSAL"
PHASE31_ARCH = "MOMENTUM_DISPLACEMENT"

BODY_MULTIPLIER = 1.5
BODY_AVG_LOOKBACK = 20
CLOSE_LOC_LONG_MIN = 0.80
CLOSE_LOC_SHORT_MAX = 0.20

FAILURE_WINDOWS = (1, 2, 3, 4)
OPP_BOS_MAX_BARS = 12
CLASSIFY_HORIZON = 8

ENTRY_MODELS = (
    "CONFIRM_CLOSE",
    "NEXT_CLOSE",
    "BOS_RETEST",
    "RECLAIM_RETEST",
)

STOP_ATRS = (0.75, 1.0, 1.25)
TARGET_RS = (1.5, 2.0, 2.5, 3.0)
HOLD_MINUTES = (30, 45, 60, 90)
MANAGEMENT = "FIXED"

# Walk-forward shortlist — small, preregistered
WF_FAILURE_DEFS = (
    "A_MID_2",
    "A_MID_3",
    "A_MID_4",
    "B_OPEN_2",
    "B_OPEN_3",
    "B_OPEN_4",
    "C_EXT_MID_3",
    "C_EXT_OPEN_3",
    "D_OPP_BOS",
    "E_MID_BOS",
    "E_OPEN_BOS",
)

WF_EXECUTION_GRID = tuple(
    {
        "entry_model": entry,
        "stop_atr": stop,
        "target_r": target,
        "hold_minutes": hold,
        "management": MANAGEMENT,
    }
    for entry in ENTRY_MODELS
    for stop in STOP_ATRS
    for target in TARGET_RS
    for hold in HOLD_MINUTES
    if (entry, stop, target, hold)
    in {
        ("CONFIRM_CLOSE", 0.75, 3.0, 60),
        ("CONFIRM_CLOSE", 1.0, 2.0, 60),
        ("CONFIRM_CLOSE", 1.25, 2.5, 60),
        ("NEXT_CLOSE", 0.75, 3.0, 60),
        ("NEXT_CLOSE", 1.0, 2.5, 60),
        ("BOS_RETEST", 0.75, 3.0, 60),
        ("BOS_RETEST", 0.75, 2.0, 60),
        ("BOS_RETEST", 1.0, 2.5, 60),
        ("BOS_RETEST", 1.25, 3.0, 90),
        ("RECLAIM_RETEST", 0.75, 3.0, 60),
        ("RECLAIM_RETEST", 1.0, 2.0, 60),
        ("RECLAIM_RETEST", 1.25, 2.5, 60),
        ("BOS_RETEST", 0.75, 1.5, 30),
        ("BOS_RETEST", 1.0, 3.0, 60),
        ("CONFIRM_CLOSE", 0.75, 2.0, 45),
        ("NEXT_CLOSE", 0.75, 1.5, 30),
        ("RECLAIM_RETEST", 0.75, 2.5, 45),
        ("BOS_RETEST", 1.0, 2.0, 45),
        ("CONFIRM_CLOSE", 1.0, 3.0, 90),
        ("BOS_RETEST", 1.25, 2.0, 60),
        ("RECLAIM_RETEST", 1.0, 3.0, 90),
        ("BOS_RETEST", 0.75, 2.5, 60),
        ("NEXT_CLOSE", 1.25, 3.0, 90),
        ("CONFIRM_CLOSE", 0.75, 1.5, 30),
    }
)

PHASE31_BENCHMARK = {
    "N": 2873,
    "AvgR": 0.233,
    "PF": 1.47,
    "MaxDD": 15.1,
    "trades_day": 1.22,
}
