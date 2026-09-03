"""Phase 47 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase47" / "results" / "1m_price_action"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_DATASET = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "one_minute_execution_dataset.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"
P45_PARAMS = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "parameter_stability.csv"

P44_PARITY = {
    "N": 2275, "L": 1015, "S": 943, "RL": 158, "RS": 159,
    "AvgR": 0.5683200798575244, "PF": 2.430042753194928,
    "TotalR": 1292.928181675868, "MaxDD": 15.563767849085934,
    "tol_AvgR": 0.001, "tol_PF": 0.01,
}

P45_B_PARITY = {
    "N": 1135, "AvgR": 1.6483731365801972, "PF": 17.77573512839063,
    "MaxDD": 8.38599731970504, "fill_rate": 0.6452529846503695,
    "wrong_direction": 0.06696035242290749, "median_delay": 1.0,
    "tol_N": 5, "tol_AvgR": 0.02, "tol_PF": 0.5, "tol_fill_rate": 0.02,
}

# Train-only parameter grids (independent tests)
BREAK_STRENGTH_MIN_ATR = (0.05, 0.10, 0.15, 0.20, 0.30)
BODY_RANGE_MIN = (0.40, 0.50, 0.60, 0.70)
RANGE_ATR_MIN = (0.50, 0.75, 1.00, 1.25, 1.50)
BODY_ATR_MIN = (0.25, 0.50, 0.75)
CLOSE_QUALITY_MIN = (0.50, 0.60, 0.70, 0.80)
OPPOSING_WICK_MAX = (0.30, 0.40, 0.50, 0.60)
RETEST_TOL_ATR = (0.10, 0.25, 0.50)
PIVOT_LOOKBACK = (3, 5, 7)
FOLLOW_THROUGH_PCT = (0.50, 0.75)

STRUCTURE_TOUCHES_MIN = (1, 2, 3)
STRUCTURE_AGE_MIN = (2, 3, 5)

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
