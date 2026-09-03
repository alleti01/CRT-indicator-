"""Phase57D — Point-in-Time Options / IV Wall Discovery configuration.

Independent research branch. Does NOT modify Phase57B, S54, or CORE.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE57D_ROOT = ROOT / "phase57d"
DATA = PHASE57D_ROOT / "data"
RESEARCH = PHASE57D_ROOT / "research"
RESULTS = PHASE57D_ROOT / "results"
REPORTS = PHASE57D_ROOT / "reports"
TESTS = PHASE57D_ROOT / "tests"

TIMEZONE = "America/Chicago"

# Walk-forward folds (identical to Phase53/57)
WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
)
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-26"

# Standardized trade (continuity with project)
STOP_ATR = 0.75
TARGET_R = 2.5
MAX_HOLD_MIN = 60
STOP_ATR_GRID = (0.5, 0.75, 1.0)
TARGET_R_GRID = (2.0, 2.5, 3.0)
COST_MULTIPLIERS = (1.0, 1.5, 2.0)

# Entry stages
ENTRY_STAGES = ("E0", "E1", "E2", "E3", "E4")

# Outcome horizons (labels only — never for signal construction)
OUTCOME_HORIZONS = (5, 10, 15, 30, 60)

# Wall families (predeclared — no mining)
WALL_FAMILIES = (
    "CALL_WALL",       # WALL A
    "PUT_WALL",        # WALL B
    "GAMMA_WALL",      # WALL C
    "IV_WALL",         # WALL D — only if IV methodology defined
    "OI_WALL",         # WALL E
    "ZERO_GAMMA",      # WALL F
    "MULTI_EXP",       # WALL G
)

# Interaction families (predeclared)
INTERACTION_FAMILIES = (
    "W1_REJECTION",
    "W2_BREAKOUT",
    "W3_BREAK_ACCEPTANCE",
    "W4_BREAK_RETEST",
    "W5_SWEEP_RECLAIM",
    "W6_PINNING",
    "W7_ROLE_FLIP",
    "W8_DECELERATION",
    "W9_ACCELERATION",
    "W10_MIGRATION",
    "W11_CLUSTER",
    "W12_VACUUM",
)

# Expiration buckets (predeclared aggregates)
EXPIRATION_BUCKETS = {
    "0DTE": (0, 0),
    "1DTE": (1, 1),
    "2-5DTE": (2, 5),
    "6-14DTE": (6, 14),
    "15-30DTE": (15, 30),
    "31-60DTE": (31, 60),
}
EXPIRATION_AGGREGATES = ("0DTE", "0-5D", "0-14D", "<=30D")

# Options → underlying mappings (test independently)
MAPPINGS = ("MAP_NQ_NQOPT", "MAP_NQ_NDX", "MAP_NQ_QQQ")

# Normalization
TOUCH_PROXIMITY_ATR = 0.25
BREAK_THRESHOLD_ATR = 0.10
EPISODE_RESET_ATR = 1.0
EPISODE_WINDOW_MIN = 30

# Wall strength
WALL_TOP_N = 5
WALL_MIN_STRENGTH_PERCENTILE = 90.0

# Session buckets (CT)
SESSION_BUCKETS = {
    "pre-08:30": ("00:00", "08:30"),
    "08:30-09:00": ("08:30", "09:00"),
    "09:00-10:00": ("09:00", "10:00"),
    "10:00-11:30": ("10:00", "11:30"),
    "11:30-13:00": ("11:30", "13:00"),
    "13:00-14:00": ("13:00", "14:00"),
    "14:00-15:00": ("14:00", "15:00"),
    "post-15:00": ("15:00", "23:59"),
}

# Distance bins (ATR-normalized)
DISTANCE_BINS = ((0, 0.25), (0.25, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, float("inf")))

# Frozen references (read-only — DO NOT MODIFY)
S54_MODEL_HASH = "bccf4277f3d44d13"
PHASE55_FROZEN = ROOT / "phase55" / "frozen"
PHASE57B_ROOT = ROOT / "phase57b"

# Method version for reproducibility
METHOD_VERSION = "phase57d_v1.0.0"

# Truncation adversarial test sample size
TRUNCATION_SAMPLE_SIZE = 10_000

# Required options fields for point-in-time research
REQUIRED_OPTIONS_FIELDS = (
    "option_symbol",
    "underlying",
    "timestamp",
    "expiration",
    "strike",
    "call_put",
    "bid",
    "ask",
    "mid",
    "last",
    "iv",
    "oi",
    "volume",
    "delta",
    "gamma",
    "vega",
    "theta",
    "underlying_price",
    "multiplier",
)
