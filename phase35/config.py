"""Phase 35 entry re-discovery configuration — preregistered before discovery."""

from __future__ import annotations

from pathlib import Path

from phase29.config import (
    COMMON_END,
    COMMON_START,
    NQ_DOLLARS_PER_POINT,
    ROUND_TURN_COST_USD,
    WALK_FORWARD_FOLDS,
    hold_bars,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase35" / "results" / "entry_rediscovery"

RTH_SESSION = "0930-1600"
PHASE_LABEL = "DEVELOPMENT / DISCOVERY"

# Primary labeling geometry (preregistered)
PRIMARY_STOP_ATR = 0.75
ALT_STOP_ATR = 1.0
PRIMARY_TARGET_RS = (1.5, 2.0, 2.5, 3.0)
PRIMARY_HORIZONS_MIN = (45, 60, 90, 120)

# Economic label thresholds (target R before 1R loss)
LABEL_STRONG_TARGET_R = 2.0
LABEL_GOOD_TARGET_R = 1.5
LABEL_STRONG_ALT_RS = (2.5, 3.0)

# Primary discovery / simulation stack (frozen before WF)
DISCOVERY_STOP_ATR = 0.75
DISCOVERY_TARGET_R = 2.0
DISCOVERY_HOLD_MINUTES = 60
DISCOVERY_MAX_BARS = hold_bars(DISCOVERY_HOLD_MINUTES)
DISCOVERY_ENTRY_MODEL = "CURRENT"

# Frequency bands for frontier reporting
FREQ_BANDS = (0.25, 0.5, 1.0, 1.5, 2.0)

# Precision curve percentiles
PRECISION_TOP_PCTS = (50, 30, 20, 10, 5, 2, 1)

# Walk-forward gates
WF_MIN_TRAIN_STRONG = 100
WF_MIN_TEST_STRONG = 20

# Success gates
GATE_MIN_N = 500
GATE_MIN_AVGR = 0.15
GATE_MIN_PF = 1.35

# Benchmark paths
PHASE31_WF_TRADES = ROOT / "phase31" / "results" / "daily_frequency_entry" / "walk_forward_trades.csv"
PHASE33_WF_TRADES = ROOT / "phase33" / "results" / "displacement_failure_reversal" / "walk_forward_trades.csv"
