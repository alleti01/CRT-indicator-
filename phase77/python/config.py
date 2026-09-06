"""Phase77 preregistered configuration — Orochi-style confluence framework (Jan 2024 pilot)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE77 = ROOT / "phase77"
DATA_DIR = PHASE77 / "data"
REPORTS = PHASE77 / "reports"
CHECKPOINTS = PHASE77 / "checkpoints"
DIAGNOSTICS = PHASE77 / "diagnostics"
EXAMPLES = PHASE77 / "examples"

TRADES_PILOT = ROOT / "phase27" / "data" / "raw" / "nq_trades_pilot_202401.csv"
M1_PILOT = ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_20231201_20260626.csv"

PILOT_START = "2024-01-01"
PILOT_END = "2024-02-01"

SYMBOL = "NQ.v.0"
TIMEZONE = "America/New_York"
PROFILE_BIN_SIZE = 1.0
VALUE_AREA_PCT = 0.70
PROFILE_TYPE = "TRUE_TRADE_VAP_PROFILE"

RTH_OPEN = (9, 30)
RTH_CLOSE = (16, 0)
OPENING_RANGE_MINUTES = 30
OVERNIGHT_START = (18, 0)

ATR_PERIOD = 14
ENTRY_DELAY_BARS = 1

# Order-flow windows (fixed)
OF_WINDOWS_SEC = (15, 30, 60)
OF_PRIMARY_SEC = 60

# Structure (frozen, not optimized)
IMPULSE_MIN_ATR = 1.0
RETRACE_MIN_RATIO = 0.25
RETRACE_MAX_RATIO = 0.62
SWING_LOOKBACK = 5

# Acceptance / rejection (from Phase76 — frozen)
ACCEPT_MIN_BARS_OUTSIDE = 3
ACCEPT_MIN_CLOSES_OUTSIDE = 2
REJECT_MAX_BARS_OUTSIDE = 5

# Price response thresholds (frozen)
EFFICIENT_DISP_PER_NORM_DELTA = 0.15
INEFFICIENT_DISP_PER_NORM_DELTA = 0.05

# Absorption proxy (frozen)
ABSORPTION_MIN_BUY_NORM = 0.25
ABSORPTION_MAX_UP_DISP = 0.15

# Confirmation
CONFIRMATION_SWING_BARS = 5
LATE_CONFIRMATION_FRAC = 0.60  # move before confirm > 60% of 15m total → TOO_LATE

# Pilot split
TRAIN_FRAC = 0.60
VAL_FRAC = 0.20

# Random direction gate
RANDOM_SEED_COUNT = 100
RANDOM_SEED_START = 77001
MIN_EFFECT_FP11 = 0.015
MIN_N_SETUP = 30

# Matched control
MAX_SMD_ACCEPT = 0.10
MATCH_SEED = 77099

# Management (only if information gate passes)
STOP_ATR_GRID = (1.0, 1.25, 1.5)
TARGET_R_GRID = (2.0, 2.5)
MAX_HOLD_MINUTES = 60
COST_BASE_POINTS = 2.0  # NQ round-trip diagnostic

MAX_EXPERIMENTS = 50

CAUSALITY_RTOL = 1e-9
CAUSALITY_ATOL = 1e-6
