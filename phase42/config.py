"""Phase 42 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase42" / "results" / "sparse_missed_reversal"

RTH_SESSION = "0930-1600"

P41_RESULTS = ROOT / "phase41" / "results" / "major_reversal_discovery"
P41_OPPORTUNITIES = P41_RESULTS / "major_reversal_opportunities.csv"
P41_CAPTURE = P41_RESULTS / "existing_system_capture.csv"
P41_MISSED = P41_RESULTS / "missed_reversal_population.csv"

P37_MAP = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "pine_reference_map.csv"
P40_MAP = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "pine_reference_map.csv"

# Frozen execution reference (Phase 33 reversal)
STOP_ATR = 0.75
TARGET_R = 2.5
MAX_HOLD_BARS = 3  # 45m
LABEL_RISK_ATR = 0.75

# Frequency gates
TARGET_TPD_MIN = 0.10
TARGET_TPD_PREF = 0.50
MAX_TPD = 0.75

# Precision tiers (train score percentiles to evaluate)
PRECISION_TIERS = (0.995, 0.99, 0.98, 0.95, 0.90)

# Success gates
MIN_OOS_N = 200
MIN_AVGR = 0.15
MIN_PF = 1.30
MIN_PF_NEW_ONLY = 1.20

# Monte Carlo
MC_SIMS = 10000

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
