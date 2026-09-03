"""Phase 29 configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from phase16.config import FrozenConfig

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase29" / "results" / "crt_v2_15m_optimization"

NQ_5M_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

CHART_MINUTES = 15
COMMON_START = "2018-01-01"
COMMON_END = "2026-06-26"

VARIANT_ID = "V2-B-LEGACY-EXP6"

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
RETRACE_WINDOW_BARS = 2
BOS_RETEST_TOLERANCE_ATR = 0.10

STOP_ATRS = (0.75, 1.0, 1.25, 1.5, 1.75, 2.0)
TARGET_RS = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
HOLD_MINUTES = (30, 45, 60, 90, 120, 180)
MANAGEMENT_MODELS = (
    "FIXED",
    "BE_AFTER_1R",
    "PARTIAL_1R",
    "PARTIAL_1R_BE",
    "TRAIL_AFTER_1R",
)

BASELINE_STOP_ATR = 1.5
BASELINE_TARGET_R = 2.0
BASELINE_HOLD_MINUTES = 60

ERAS = (
    ("ERA1", "2018-01-01", "2020-12-31"),
    ("ERA2", "2021-01-01", "2023-12-31"),
    ("ERA3", "2024-01-01", "2026-06-26"),
)

WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2018-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ("2018-01-01", "2025-12-31", "2026-01-01", "2026-06-26"),
)

PARITY = {
    "N": 210,
    "net_AvgR": 0.094,
    "net_TotalR": 20.0,
    "net_PF": 1.31,
    "MaxDD": 5.6,
    "tol_N": 15,
    "tol_AvgR": 0.025,
    "tol_TotalR": 5.0,
    "tol_PF": 0.08,
    "tol_MaxDD": 2.0,
}


def frozen_config_15m() -> FrozenConfig:
    return replace(FrozenConfig(), chart_minutes=CHART_MINUTES)


def hold_bars(minutes: int) -> int:
    return max(1, round(minutes / CHART_MINUTES))
