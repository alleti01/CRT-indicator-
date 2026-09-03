"""Configuration for 1m execution study."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "phase45" / "results" / "15m_context_1m_execution"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P40_MAP = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "filtered_signal_map.csv"

P44_PARITY = {
    "N": 2275,
    "AvgR": 0.5683200798575244,
    "PF": 2.430042753194928,
    "TotalR": 1292.928181675868,
    "MaxDD": 15.563767849085934,
    "tol_AvgR": 0.001,
    "tol_PF": 0.01,
    "tol_TotalR": 0.5,
    "tol_MaxDD": 0.1,
}

CHART_15M = 15
EXEC_WINDOWS_MIN = (5, 10, 15)
PRICE_RULES = ("B1", "B2", "B3", "B4")
SWING_LOOKBACK = 3

MAX_HOLD_CONT = 60
MAX_HOLD_REV = 45

# Volume threshold candidates (selected train-only per fold)
VOL_THRESHOLDS = (0.8, 1.0, 1.2, 1.5)

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402

RAW_1M_PATHS = (
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_oos_20171001_20201201.csv",
    ROOT / "phase18" / "data" / "raw" / "nq_continuous_1m_raw.csv",
    ROOT / "phase16" / "data" / "raw" / "nq_continuous_1m_20231201_20260626.csv",
)
