"""Phase 28 configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from phase16.config import FrozenConfig

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase28" / "results" / "multi_timeframe_strategy"

NQ_5M_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

TIMEFRAMES = (5, 15, 30, 60)
COMMON_START = "2018-01-01"
COMMON_END = "2026-06-26"

ERAS = (
    ("ERA1", "2018-01-01", "2020-12-31"),
    ("ERA2", "2021-01-01", "2023-12-31"),
    ("ERA3", "2024-01-01", "2026-06-26"),
)

PARITY_WINDOWS = (
    ("RETEST_GATED", "Confirm", "2024-01-01", "2026-06-26", 705, 20),
    ("BOS_ONLY", "BOS", "2021-01-01", "2026-06-26", 4150, 100),
    ("CRT_V2", "CRT_V2", "2024-01-01", "2026-06-26", 193, 10),
)

ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0

STRATEGIES_INCLUDED = (
    "CONTROL",
    "RETEST_GATED",
    "BOS_ONLY",
    "SEQUENTIAL_BOS",
    "CRT_V2_B_LEGACY_EXP6",
)

STRATEGIES_EXCLUDED = (
    "HIGH_EXPECTANCY (Phase 26 bar-level ML — not a standalone trade architecture; Classification D)",
    "ENTRY_PRECISION (Phase 24 ML ranker on frozen CRT — not a standalone architecture; Classification C)",
)


def config_for_timeframe(minutes: int) -> FrozenConfig:
    return replace(FrozenConfig(), chart_minutes=minutes)
