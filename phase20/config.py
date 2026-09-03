"""Phase 20 discovery configuration — not frozen strategy parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase20" / "results" / "session_liquidity_edge"

# Fixed interaction geometry (documented; not optimized).
APPROACH_ATR = 0.25
RESET_ATR = 0.50

# Opening range: first 30 minutes of RTH (09:30–10:00 America/Chicago).
OR_START_MINUTE = 9 * 60 + 30
OR_END_MINUTE = 10 * 60 + 0  # exclusive upper bound at 10:00 bar open

HORIZONS = (1, 3, 6, 12, 24)

LEVELS = (
    "PDH",
    "PDL",
    "ONH",
    "ONL",
    "ORH",
    "ORL",
    "PRIOR_RTH_CLOSE",
    "SESSION_OPEN",
)

EVENT_TYPES = (
    "APPROACH",
    "TOUCH",
    "SWEEP",
    "BREAK",
    "BREAK_HOLD",
    "BREAK_FAILURE",
)

# Phase 20 time buckets (America/Chicago, bar open time).
TIME_BUCKETS: Dict[str, Tuple[int, int]] = {
    "OVERNIGHT": (18 * 60, 4 * 60),  # wraps midnight
    "PREMARKET": (4 * 60, 9 * 60 + 30),
    "RTH_OPEN": (9 * 60 + 30, 10 * 60 + 30),
    "RTH_MID_MORNING": (10 * 60 + 30, 12 * 60),
    "MIDDAY": (12 * 60, 14 * 60),
    "RTH_AFTERNOON": (14 * 60, 16 * 60),
}

ERAS = {
    "era1": ("2018-01-01", "2020-11-30"),
    "era2": ("2021-01-01", "2023-12-29"),
    "era3": ("2024-01-01", "2026-06-26"),
}

CONTAMINATED_WINDOWS = (
    "2018-01-01 → 2020-11-30 (CRT failed-OOS observed)",
    "2021-01-01 → 2023-12-29 (Phase 18 OOS observed)",
    "2024-01-01 → 2026-06-26 (CRT development observed)",
    "2026-06-29 → 2026-08-18 (parity observed)",
)

DATA_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)


@dataclass(frozen=True)
class ReplicationCriteria:
    min_total_n: int = 300
    min_era_n: int = 75
    min_positive_eras: int = 2
    max_era_contribution: float = 0.60
    min_full_sample_atr: float = 0.05
