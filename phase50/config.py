"""Phase 50 — Pine parity configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase50" / "results" / "pine_parity"
PINE_DIR = ROOT / "phase50" / "pine"

# Frozen model (matches Phase49 / Phase45 production candidate)
FROZEN_B1_RULE = "B1"
FROZEN_B1_WINDOW_MIN = 10
CHART_15M_MIN = 15
TIMEZONE = "America/Chicago"
RTH_SESSION = "0930-1600"
INSTRUMENT = "NQ"
TICK_SIZE = 0.25
PRICE_TOLERANCE = TICK_SIZE  # NQ tick-aware

# M0 (from phase45/execution/simulate.py)
MAX_HOLD_CONT_1M = 60
MAX_HOLD_REV_1M = 45
TARGET_R_CONT = 3.0
TARGET_R_REV = 2.5

# Python data source (Databento continuous NQ.v.0, America/Chicago)
PYTHON_DATA_SOURCE = "Databento NQ continuous (phase16/phase18 stitched 1m/5m)"
TV_SYMBOL_RECOMMENDATION = "CME_MINI:NQ1! or continuous NQ futures matching CME ETH session"

P44_REF = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"
P44_PINE = ROOT / "phase44" / "results" / "quality_filtered_pine" / "NQ15_PHASE44_QUALITY_INDICATOR.pine"

HISTORICAL = {
    "phase44": {"N": 2275, "AvgR": 0.568, "PF": 2.43},
    "b1_stitched": {"N": 1135, "AvgR": 1.648, "PF": 17.78, "MaxDD": 8.39},
    "b1_w10": {"N": 1212},
    "m0": {"TotalR": 1871, "WinRate": 0.866, "N": 1135},
}

SAMPLE_MIN_PER_SEGMENT = 10
