"""Phase78 preregistered Silver Bullet configuration — not tuned from results."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE78 = ROOT / "phase78"
DATA_DIR = PHASE78 / "data"
REPORTS = PHASE78 / "reports"
CHECKPOINTS = PHASE78 / "checkpoints"
DIAGNOSTICS = PHASE78 / "diagnostics"
EXAMPLES = PHASE78 / "examples"

# Data — same stitched stack, loader only (no trading logic)
RAW_1M_PATHS = (
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_oos_20171001_20201201.csv",
    ROOT / "phase18" / "data" / "raw" / "nq_continuous_1m_raw.csv",
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_20231201_20260626.csv",
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_postwindow_to_20260629T0000CT.csv",
    ROOT / "phase58j" / "data" / "nq_continuous_1m_lw_extension.csv",
)

SYMBOL = "NQ.v.0"
CONTINUOUS_METHOD = "Databento GLBX.MDP3 volume continuous (NQ.v.0)"
TIMEZONE = "America/New_York"
TIMEZONE_UTC = "UTC"

RTH_OPEN = (9, 30)
RTH_CLOSE = (16, 0)
OVERNIGHT_START = (18, 0)

ATR_PERIOD = 14
ENTRY_DELAY_BARS = 1

# Silver Bullet windows (ET) — frozen
SB_WINDOWS = {
    "SB1": ((3, 0), (4, 0)),
    "SB2": ((10, 0), (11, 0)),
    "SB3": ((14, 0), (15, 0)),
}

# Causal pivot for swings — confirmed after PIVOT_RIGHT bars
PIVOT_LEFT = 3
PIVOT_RIGHT = 2

# Equal high/low tolerance (ATR-normalized) — diagnostic primary 0.10
EQ_TOL_ATR = (0.05, 0.10)
EQ_TOL_PRIMARY = 0.10

# Displacement bands (ATR) — primary 0.75
DISPLACEMENT_ATR = (0.5, 0.75, 1.0)
DISPLACEMENT_PRIMARY = 0.75
DISPLACEMENT_MAX_BARS = 12

# MSS lookbacks — primary 5
MSS_LOOKBACKS = (3, 5, 10)
MSS_PRIMARY = 5
MSS_MAX_BARS_AFTER_DISP = 15

# FVG — canonical 3-candle, max bars after MSS to form
FVG_MAX_BARS_AFTER_MSS = 8

# Entry modes
ENTRY_MODES = ("FVG_TOUCH", "FVG_MIDPOINT")
ENTRY_PRIMARY = "FVG_TOUCH"

# Targets (R multiples)
TARGET_R = (2.0, 2.5)

# Random direction gate
RANDOM_SEED_COUNT = 100
RANDOM_SEED_START = 78001
MIN_EFFECT_FP11 = 0.012
MIN_N_ENTRIES = 100

# Splits
TRAIN_FRAC = 0.60
VAL_FRAC = 0.20

# Costs (NQ points round-trip diagnostic)
COST_BASE_POINTS = 2.0

# Causality
PREFIX_CUTOFFS = (0.25, 0.50, 0.75)
CAUSALITY_RTOL = 1e-9
CAUSALITY_ATOL = 1e-6

MAX_EXPERIMENTS = 50

# Path horizons (minutes)
PATH_HORIZONS = (3, 5, 10, 15, 30, 60)
