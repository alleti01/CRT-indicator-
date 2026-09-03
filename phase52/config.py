"""Phase52 — S52 secondary intraday structure research configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE52_ROOT = ROOT / "phase52"
RESULTS = PHASE52_ROOT / "results" / "intraday_structure"
RESEARCH = PHASE52_ROOT / "research"

TIMEZONE = "America/Chicago"
RTH_SESSION = "0930-1600"
NQ_TICK = 0.25

# Data (same sources as Phase45/Phase49)
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"
P44_ACCEPTED = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"

# Walk-forward folds (Phase29 — unchanged)
WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2018-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ("2018-01-01", "2025-12-31", "2026-01-01", "2026-06-26"),
)

# ═══ S52 STANDARDIZED EXIT (frozen BEFORE candidate comparison) ═══
# M0 uses Phase44 stop geometry; S52 uses fixed causal ATR framework.
S52_STOP_ATR = 0.75
S52_TARGET_R = 2.5
S52_MAX_HOLD_MIN = 60
S52_SIGNAL_TYPE = "S52"

# Structure parameters (small grid)
SWING_LOOKBACKS = (3, 5, 7)
DEFAULT_SWING = 5
ATR_BREAK_MULTS = (0.0, 0.10)
DISPLACEMENT_BODY_MULT = 1.5
RANGE_LOOKBACK_15M = 20

# Context labels
CONTEXTS = ("C0", "C1", "C2", "C3", "C4", "C5")

# Families under test
FAMILIES = (
    "A1", "A2", "A3", "B1", "B2", "C1", "D1", "E1", "F1", "G1", "G3",
)

# CORE overlap window (defined before analysis)
CORE_OVERLAP_MIN = 30

# Opportunity coverage definitions (analysis labels only — not signal inputs)
COVERAGE_DEFS = (
    {"name": "M1_60", "mfe_atr": 1.0, "mae_atr": 0.75, "horizon_min": 60},
    {"name": "M1.5_90", "mfe_atr": 1.5, "mae_atr": 1.0, "horizon_min": 90},
)

# Selection constraints (train-only)
MIN_TRAIN_TRADES = 80
MIN_TEST_TRADES = 20

# CORE benchmark (Phase45 B1 WF)
CORE_BENCHMARK = {"N": 1135, "AvgR": 1.648, "PF": 17.78, "MaxDD": 8.39}
