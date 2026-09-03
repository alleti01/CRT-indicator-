"""Phase 48 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase48" / "results" / "trade_management"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_DATASET = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "one_minute_execution_dataset.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"

P44_PARITY = {
    "N": 2275, "AvgR": 0.5683200798575244, "PF": 2.430042753194928,
    "TotalR": 1292.928181675868, "MaxDD": 15.563767849085934,
    "tol_AvgR": 0.001, "tol_PF": 0.01,
}

P45_ENTRY_PARITY = {
    "N": 1135, "AvgR": 1.6483731365801972, "PF": 17.77573512839063,
    "MaxDD": 8.38599731970504, "fill_rate": 0.6452529846503695,
    "wrong_direction": 0.06696035242290749, "median_delay": 1.0,
    "tol_N": 5, "tol_AvgR": 0.02, "tol_PF": 0.5, "tol_fill_rate": 0.02,
    "tol_entry_price": 0.01,
}

# Stop grids (S3)
ATR_STOP_MULTS = (0.50, 0.75, 1.00, 1.25, 1.50, 2.00)
HYBRID_MIN_ATR = (0.50, 0.75)
HYBRID_MAX_ATR = (1.25, 1.50)
STRUCT_STOP_BUFFER_ATR = (0.10, 0.25)

# Fixed R targets (B)
FIXED_TARGET_R = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0)
STRUCT_TARGET_MIN_R = (1.0, 1.5)
STRUCT_TARGET_MAX_R = (2.5, 3.0)

# Break-even (D)
BE_TRIGGERS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)
BE_DESTS = ("BE0", "BE1", "BE2")

# Trailing (F)
TRAIL_ACTIVATE = (0.75, 1.0, 1.5, 2.0)
TRAIL_ATR = (0.5, 0.75, 1.0, 1.5)
TRAIL_GIVEBACK = (0.5, 0.75, 1.0, 1.5)

# Opposite BOS (G)
OPPOSITE_BOS_MIN_R = (0.0, 0.5, 1.0)

# Time exit (I)
TIME_EXIT_MIN = (5, 10, 15, 20, 30, 45, 60, 90, 120)

# Stagnation (J)
STAGNATION_RULES = ("ST1", "ST2", "ST3", "ST4", "ST5")

# Profit lock (K)
PROFIT_LOCK_TRIGGERS = (1.0, 1.5, 2.0, 3.0)
PROFIT_LOCK_LEVELS = (0.0, 0.5, 1.0, 1.5)

# Partial schemes (E) — predefined only
PARTIAL_SCHEMES = {
    "P1": [(1.0, 0.25)],
    "P2": [(1.0, 0.50)],
    "P3": [(1.5, 0.50)],
    "P4": [(1.0, 0.33), (2.0, 0.33)],
    "P5": [(1.0, 0.50)],  # + BE on runner handled separately
    "P6": [(1.0, 0.25), (2.0, 0.25)],
}

TARGET_R_CONT = 3.0
TARGET_R_REV = 2.5

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
from phase45.execution.config import MAX_HOLD_CONT, MAX_HOLD_REV  # noqa: E402
