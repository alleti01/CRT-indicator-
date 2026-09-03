"""Phase 26 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase26" / "results" / "high_expectancy_entry"

NQ_DATA_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

RESEARCH_START = "2018-01-01"
RESEARCH_END = "2026-06-26"

HORIZON_MINUTES = (15, 30, 45, 60, 90, 120)
HORIZON_BARS = tuple(int(m / 5) for m in HORIZON_MINUTES)
PRIMARY_HORIZON_BARS = 24  # 120m

PROFIT_ATR_LEVELS = (0.5, 0.75, 1.0, 1.5, 2.0)
LOSS_ATR_LEVELS = (0.5, 0.75, 1.0, 1.5)

PRIMARY_PROFIT_ATR = 1.0
PRIMARY_LOSS_ATR = 0.5

SECONDARY_TARGETS = (
    (1.0, 1.0),
    (1.5, 0.75),
    (1.5, 1.0),
    (2.0, 1.0),
)

ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0
RISK_ATR_FOR_COST = 0.5  # primary stop distance in ATR

WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ("2018-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ("2018-01-01", "2025-12-31", "2026-01-01", "2026-06-26"),
)

PRECISION_FRACTIONS = (0.50, 0.30, 0.20, 0.10, 0.05, 0.02, 0.01)
PIVOT_LEFT = 5
