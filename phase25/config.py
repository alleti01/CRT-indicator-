"""Phase 25 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase25" / "results" / "bos_trade_optimization"

TRADE_SOURCES = (
    ROOT / "phase18/results/base_run/trades.csv",
    ROOT / "phase17/results/baseline_run/trades.csv",
)

NQ_DATA_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0

ENTRY_MODELS = (
    "CURRENT",
    "NEXT_OPEN",
    "NEXT_CLOSE",
    "RETRACE_25",
    "RETRACE_50",
    "BOS_RETEST",
)

STOP_ATRS = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
TARGET_RS = (1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
HOLD_MINUTES = (30, 45, 60, 90, 120)

MANAGEMENT_MODELS = (
    "FIXED",
    "BE_AFTER_1R",
    "PARTIAL_1R",
    "PARTIAL_1R_BE",
    "TRAIL_AFTER_1R",
)

PATH_HORIZONS = (1, 2, 3, 6, 12, 18, 24, 36)
R_LEVELS = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
LOSS_LEVELS = (0.25, 0.5, 0.75, 1.0)

RETRACE_WINDOW_BARS = 8
BOS_RETEST_TOLERANCE_ATR = 0.10

WALK_FORWARD_FOLDS = (
    ("2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2021-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ("2021-01-01", "2025-12-31", "2026-01-01", "2026-06-26"),
)

MC_SIMULATIONS = 10_000
