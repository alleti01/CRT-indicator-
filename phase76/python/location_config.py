"""Phase76 S/R location control — preregistered thresholds (not tuned from results)."""
from __future__ import annotations

# Frozen distance bands (ATR-normalized) — do not optimize beyond these.
DISTANCE_BANDS_ATR = (0.10, 0.25, 0.50)

# Primary band for matching / head-to-head (middle band)
PRIMARY_BAND_ATR = 0.25

# Exclusion band for non-level pool: bar must be outside ALL auction levels by this margin
NON_LEVEL_EXCLUSION_ATR = 0.25

# Path horizons (minutes on 1m bars)
PATH_HORIZONS = (5, 10, 15, 30, 60)
THRESHOLD_ATR_LEVELS = (0.5, 1.0, 1.5, 2.0, 2.5)

# Clean expansion: one side expands while opposite remains limited (15m window)
CLEAN_EXP_MAJOR_ATR = 1.0
CLEAN_EXP_OPPOSITE_MAX_ATR = 0.35
CLEAN_EXP_HORIZON = 15

# Rejection / rotation proxy horizon
REJECTION_HORIZON = 15

# Continuation / failure after first 1.0 ATR break
FIRST_BREAK_ATR = 1.0
CONTINUATION_EXT_ATR = 0.5
CONTINUATION_HORIZON = 30

# Matched-control quality
MAX_SMD_ACCEPT = 0.10  # standardized mean difference — above → CONTROL_MATCH_FAIL
MATCH_TIME_BIN_MINUTES = 30
MATCH_SEED = 76101

# Practical effect gates (location information, not directional)
MIN_ABS_EXCURSION_LIFT_15 = 0.08  # ATR mean two_sided_range or abs excursion vs matched
MIN_CLEAN_EXPANSION_LIFT = 0.03  # probability points
MIN_SWEEP_DIFF = 0.02  # meaningful sweep-rate difference
MIN_N_EVENTS = 500  # below → DATA_INSUFFICIENT
VAL_EFFECT_RATIO = 0.50  # validation effect must retain this fraction of train, same sign
MIN_YEAR_FRACTION_SAME_SIGN = 0.60
MIN_SIMPLE_SR_LIFT_FRACTION = 0.50  # profile must beat simple S/R by this fraction of own lift

# Head-to-head pairs (auction → simple counterpart)
HEAD_TO_HEAD = (
    ("PRIOR_VAH", "PRIOR_SESSION_HIGH"),
    ("PRIOR_VAL", "PRIOR_SESSION_LOW"),
    ("DEV_VAH", "PRIOR_SESSION_HIGH"),
    ("DEV_VAL", "PRIOR_SESSION_LOW"),
    ("DEV_POC", "VWAP"),
    ("PRIOR_POC", "VWAP"),
    ("DEV_VAH", "ROLL_30M_HIGH"),
    ("DEV_VAL", "ROLL_30M_LOW"),
)

# Profile vs rolling structure
PROFILE_VS_ROLLING = (
    ("DEV_VAH", "ROLL_20M_HIGH"),
    ("DEV_VAL", "ROLL_20M_LOW"),
    ("PRIOR_VAH", "ROLL_20M_HIGH"),
    ("PRIOR_VAL", "ROLL_20M_LOW"),
)
