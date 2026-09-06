"""Phase76 preregistered configuration — no tuning during discovery."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE76 = ROOT / "phase76"
DATA_DIR = PHASE76 / "data"
REPORTS = PHASE76 / "reports"
CHECKPOINTS = PHASE76 / "checkpoints"
DIAGNOSTICS = PHASE76 / "diagnostics"
EXAMPLES = PHASE76 / "examples"

# Canonical causal 1m stack (LEVEL 0) — same stitching as phase58j / phase68
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
SOURCE = "Databento ohlcv-1m (stitched local CSV)"

# RTH session (primary auction session)
RTH_OPEN = (9, 30)
RTH_CLOSE = (16, 0)
OPENING_RANGE_MINUTES = 30

# Globex overnight reference: prior 18:00 ET → current 09:29 ET
OVERNIGHT_START = (18, 0)

# Profile — BAR_APPROX only at LEVEL 0
PROFILE_BIN_SIZE = 1.0  # NQ points
VALUE_AREA_PCT = 0.70
PROFILE_TYPE = "BAR_APPROX_PROFILE"
HVN_PERCENTILE = 0.80  # top 20% volume bins
LVN_PERCENTILE = 0.20  # bottom 20% volume bins

# Acceptance / rejection (minimal fixed thresholds — not a parameter search)
ACCEPT_MIN_BARS_OUTSIDE = 3
ACCEPT_MIN_CLOSES_OUTSIDE = 2
REJECT_MAX_BARS_OUTSIDE = 5  # failed to accept within this window after test

# Entry semantics
ATR_PERIOD = 14
ENTRY_DELAY_BARS = 1  # signal on close T, entry open T+1

# Walk-forward split (chronological)
TRAIN_FRAC = 0.60
VAL_FRAC = 0.20
# remainder = PREVIOUSLY_EXPOSED_HISTORICAL_TEST

# Experiment cap
MAX_CONFIGURATIONS = 50

# Management grid (post path-audit only)
STOP_ATR_GRID = (0.75, 1.0, 1.25, 1.5)
TARGET_R_GRID = (1.5, 2.0, 2.5, 3.0)
MAX_HOLD_MINUTES = 60

# Causality audit
PREFIX_CUTOFFS = (0.25, 0.50, 0.75, 0.90)
CAUSALITY_RTOL = 1e-9
CAUSALITY_ATOL = 1e-6

# Pilot order-flow (LEVEL 1) — blocked for full history
TRADES_PILOT_PATH = ROOT / "phase27" / "data" / "raw" / "nq_trades_pilot_202401.csv"
