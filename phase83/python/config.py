"""Phase83 — overnight/premarket breakout acceptance research config."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"

# Frozen M0 — identical to project research spec. Do not change.
M0 = {
    "stop_r": 1.0,
    "target_r": 2.5,
    "max_hold_minutes": 60,
    "collision": "STOP_FIRST",
}

NY_TZ = "America/New_York"
EXCHANGE_TZ = "America/Chicago"

# Overnight / premarket: 18:00 previous trading day → 09:29 ET current
ON_START_HOUR, ON_START_MINUTE = 18, 0
ON_END_HOUR, ON_END_MINUTE = 9, 29
RTH_OPEN_HOUR, RTH_OPEN_MINUTE = 9, 30
RTH_CLOSE_HOUR, RTH_CLOSE_MINUTE = 16, 0
RESEARCH_END_HOUR, RESEARCH_END_MINUTE = 11, 0

MIN_OVERNIGHT_BARS = 60
MIN_PRIOR_RTH_BARS = 60
ATR_PERIOD = 14

TIME_BUCKETS = (
    ("0930_0935", 9, 30, 9, 35),
    ("0935_0945", 9, 35, 9, 45),
    ("0945_1000", 9, 45, 10, 0),
    ("1000_1030", 10, 0, 10, 30),
    ("1030_1100", 10, 30, 11, 0),
)

# Chronological partitions by session date
TRAIN_FRAC = 0.60
VALID_FRAC = 0.80

MIN_FULL = 500
MIN_VAL = 150
MIN_TEST = 150

# Coarse Stage-2 thresholds (not optimized)
BODY_FRACTIONS = (0.40, 0.55, 0.70)
DIST_ATR = (0.0, 0.05, 0.10, 0.20)
VOL_RATIOS = (1.0, 1.25, 1.50)

RETEST_ATR = 0.20
RESET_ATR = 0.15
EXTENDED_ATR = 0.20
B6_MAX_WAIT = 30
B7_MAX_WAIT = 30
F2_RETURN_BARS = 5
F4_DISP_ATR = 0.10
F4_DISP_BARS = 3

# Volume baseline: last N completed 2M bars
VOL_LOOKBACK_2M = 20

# Random / bootstrap
CONTROL_SEEDS = 20
CAUSALITY_SAMPLES = 500
CAUSALITY_SEED = 83

# Slippage sensitivity (extra ticks adverse on top of NQ.cost_r)
SLIP_TICKS = (0, 1, 2)
TICK_SIZE = 0.25

STAGE1 = ("B0", "B1", "B2", "F1", "F2")
STAGE2 = ("B3_55", "B4_10", "B5_125", "B6", "B7", "F3", "F4")
