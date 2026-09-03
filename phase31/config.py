"""Phase 31 configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from phase16.config import FrozenConfig
from phase29.config import (
    COMMON_END,
    COMMON_START,
    NQ_5M_PATHS,
    ROUND_TURN_COST_USD,
    WALK_FORWARD_FOLDS,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase31" / "results" / "daily_frequency_entry"

CHART_MINUTES = 15
RTH_SESSION = "0930-1600"
NQ_DOLLARS_PER_POINT = 20.0

# Execution search (small grid)
ENTRY_MODELS = ("CURRENT", "NEXT_OPEN", "BOS_RETEST")
STOP_ATRS = (0.75, 1.0, 1.25, 1.5)
TARGET_RS = (1.5, 2.0, 2.5, 3.0)
HOLD_MINUTES = (30, 45, 60, 90)
MANAGEMENT = "FIXED"

# Walk-forward shortlist (24 combos — small, economically motivated)
SHORTLIST_EXECUTION_GRID = tuple(
    {
        "entry_model": entry,
        "stop_atr": stop,
        "target_r": target,
        "hold_minutes": hold,
        "management": MANAGEMENT,
    }
    for entry in ENTRY_MODELS
    for stop in (0.75, 1.0, 1.25)
    for target in (1.5, 2.0, 2.5, 3.0)
    for hold in (30, 60, 90)
    if (entry, stop, target, hold) in {
        ("CURRENT", 0.75, 2.0, 60),
        ("CURRENT", 1.0, 2.0, 60),
        ("CURRENT", 1.25, 2.5, 60),
        ("CURRENT", 1.0, 3.0, 90),
        ("NEXT_OPEN", 0.75, 2.0, 60),
        ("NEXT_OPEN", 1.0, 2.5, 60),
        ("NEXT_OPEN", 1.25, 3.0, 90),
        ("BOS_RETEST", 0.75, 2.0, 60),
        ("BOS_RETEST", 0.75, 3.0, 60),
        ("BOS_RETEST", 1.0, 2.0, 45),
        ("BOS_RETEST", 1.0, 2.5, 60),
        ("BOS_RETEST", 1.25, 3.0, 90),
        ("CURRENT", 0.75, 1.5, 30),
        ("CURRENT", 1.0, 2.0, 45),
        ("NEXT_OPEN", 0.75, 1.5, 30),
        ("NEXT_OPEN", 1.0, 3.0, 60),
        ("BOS_RETEST", 0.75, 1.5, 30),
        ("BOS_RETEST", 1.0, 3.0, 60),
        ("CURRENT", 1.25, 2.0, 90),
        ("NEXT_OPEN", 1.25, 2.0, 90),
        ("BOS_RETEST", 1.25, 2.0, 60),
        ("CURRENT", 0.75, 3.0, 60),
        ("NEXT_OPEN", 0.75, 2.5, 45),
        ("BOS_RETEST", 1.0, 2.0, 60),
    }
)

# Dedup
MIN_BARS_BETWEEN_SAME_DIR = 4
ONE_ACTIVE_TRADE = True

# Monte Carlo
MC_SIMULATIONS = 10_000

# Frequency targets (trades per RTH day)
FREQ_BANDS = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0)

# Phase 30 frozen reference execution
PHASE30_EXEC = {
    "entry_model": "BOS_RETEST",
    "stop_atr": 0.75,
    "target_r": 3.0,
    "hold_minutes": 60,
}


def frozen_config_15m() -> FrozenConfig:
    return replace(FrozenConfig(), chart_minutes=CHART_MINUTES)


def hold_bars(minutes: int) -> int:
    return max(1, round(minutes / CHART_MINUTES))
