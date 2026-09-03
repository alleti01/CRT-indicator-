"""Phase 46 VWAP research configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase46" / "results" / "vwap"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_DATASET = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "one_minute_execution_dataset.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"

# Phase 44 parity (full accepted population)
P44_PARITY = {
    "N": 2275,
    "L": 1015,
    "S": 943,
    "RL": 158,
    "RS": 159,
    "AvgR": 0.5683200798575244,
    "PF": 2.430042753194928,
    "TotalR": 1292.928181675868,
    "MaxDD": 15.563767849085934,
    "tol_AvgR": 0.001,
    "tol_PF": 0.01,
    "tol_TotalR": 0.5,
    "tol_MaxDD": 0.1,
}

# Phase 45 Model B reference (OOS stitched walk-forward)
P45_B_PARITY = {
    "N": 1135,
    "AvgR": 1.6483731365801972,
    "PF": 17.77573512839063,
    "MaxDD": 8.38599731970504,
    "fill_rate": 0.6452529846503695,
    "tol_N": 25,
    "tol_AvgR": 0.05,
    "tol_PF": 1.0,
    "tol_MaxDD": 0.5,
    "tol_fill_rate": 0.03,
}

# B0 control: frozen B1 micro-BOS @ 10 min window
B0_RULE = "B1"
B0_WINDOW_MIN = 10
B0_PREFIX = f"{B0_RULE}_w{B0_WINDOW_MIN}"

# VWAP session: CME trading day (18:00 America/Chicago rollover)
VWAP_TIMEZONE = "America/Chicago"
VWAP_PRICE_SOURCE = "HLC3"  # (high + low + close) / 3

# V3 slope lookback candidates (minutes / bars on 1m)
V3_SLOPE_WINDOWS = (1, 3, 5, 10)

# V4 max distance from VWAP (ATR-normalized); None = no cap (side only for max)
V4_MAX_DIST_ATR = (0.25, 0.50, 0.75, 1.00, 1.50, 2.00)

# V5 retest tolerance (ATR-normalized) and max wait bars after B1
V5_TOL_ATR = (0.10, 0.25)
V5_WAIT_BARS = (3, 5)

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
