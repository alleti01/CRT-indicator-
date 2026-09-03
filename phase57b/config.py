"""Phase57B — Causal Turn Discovery configuration.

NQ-based experiment, but uses normalized concepts for future universality.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE57B_ROOT = ROOT / "phase57b"
RESULTS = PHASE57B_ROOT / "results"
REPORTS = PHASE57B_ROOT / "reports"

TIMEZONE = "America/Chicago"

# Reuse Phase53 walk-forward folds
WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
)
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-26"

# Normalized standardized trade (ATR-relative, market-agnostic)
STOP_ATR = 0.75
TARGET_R = 2.5
MAX_HOLD_MIN = 60

# Leg detection (normalized)
DEFAULT_SWING = 5
LEG_MIN_DISTANCE_ATR = 1.0

# Pullback qualification (normalized — percentage of Leg1)
PULLBACK_MIN_DEPTH_PCT = 0.15
PULLBACK_MAX_BARS = 60

# Causal turn evidence family (small, predeclared)
TURN_EVIDENCE = {
    "T0_qualification": "first bar reaching pullback threshold",
    "T1_close_reversal": "first bar closing back toward leg direction",
    "T2_body_reversal": "first bar with body > 0.3 ATR in leg direction",
    "T3_wick_rejection": "bar with wick > 50% of range rejecting pullback extreme",
    "T4_swing_reclaim": "close reclaims the pre-pullback swing level",
}

# Episode consolidation (normalized time window)
EPISODE_WINDOW_MIN = 30

# S54 frozen reference
S54_MODEL_HASH = "bccf4277f3d44d13"
PHASE55_FROZEN = ROOT / "phase55" / "frozen"
