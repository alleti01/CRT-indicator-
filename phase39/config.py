"""Phase 39 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase39" / "results" / "entry_timing_static_precision"

P37_SIGNAL_MAP = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "pine_reference_map.csv"

# Expected populations (Phase 37/38 canonical)
EXP_L = 2075
EXP_S = 1836
EXP_RL = 976
EXP_RS = 925

# Frozen execution
P31_MAX_HOLD = 4
P33_MAX_HOLD = 3
P31_TARGET_R = 3.0
P33_TARGET_R = 2.5
STOP_ATR = 0.75

# Preregistered movement target (primary)
PRIMARY_MOVEMENT_MFE_R = 1.0

# Post-hoc behavior class thresholds (documented; sensitivity in classify.py)
CLASS_IMMEDIATE_MFE_R = 0.50
CLASS_IMMEDIATE_BARS = 1
CLASS_STATIC_MFE_R = 0.50
CLASS_STATIC_MAE_R = 0.75
CLASS_STATIC_EFFICIENCY = 0.35
CLASS_WRONG_MAE_R = 0.75
CLASS_WRONG_MFE_R = 0.25
CLASS_CLEAN_WIN_MFE_R = 1.0
CLASS_CLEAN_WIN_MAE_R = 0.35
CLASS_DELAYED_MFE_R = 0.50
CLASS_DELAYED_MIN_BARS = 2

# Static exit grid (preregistered)
STATIC_EXIT_GRID = (
    (1, 0.25),
    (2, 0.25),
    (2, 0.50),
    (3, 0.50),
)

# Retention frontier levels
RETENTION_LEVELS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3)

# Walk-forward folds (phase29)
from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402

RTH_SESSION = "0930-1600"
