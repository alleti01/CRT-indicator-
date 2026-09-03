"""Phase 22 preregistered discovery parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase22" / "results" / "auction_profile_edge"

HORIZONS = (1, 3, 6, 12, 24)
RTH_SESSION = "0930-1600"
VALUE_AREA_PCT = 0.70
PROFILE_TICK = 0.25  # NQ minimum tick; fixed bin width
RESET_ATR = 0.50
APPROACH_ATR = 0.25

ERAS = {
    "era1": ("2018-01-01", "2020-11-30"),
    "era2": ("2021-01-01", "2023-12-29"),
    "era3": ("2024-01-01", "2026-06-26"),
}

DATA_PATHS = (
    ROOT / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
    ROOT / "phase18/data/processed/nq_5m.csv",
    ROOT / "phase16/data/processed/nq_5m.csv",
)

CONTAMINATED_WINDOWS = (
    "2018-01-01 → 2020-11-30 (CRT failed-OOS observed)",
    "2021-01-01 → 2023-12-29 (Phase 18 OOS observed)",
    "2024-01-01 → 2026-06-26 (CRT development observed)",
    "2026-06-29 → 2026-08-18 (parity observed)",
)

# RTH diagnostic buckets (America/Chicago, aligned with project RTH 09:30–16:00).
RTH_TIME_BUCKETS: Dict[str, Tuple[int, int]] = {
    "RTH_0930_1030": (9 * 60 + 30, 10 * 60 + 30),
    "RTH_1030_1200": (10 * 60 + 30, 12 * 60),
    "RTH_1200_1400": (12 * 60, 14 * 60),
    "RTH_1400_1600": (14 * 60, 16 * 60),
}

OPEN_LOCATIONS = ("ABOVE_VAH", "INSIDE_VALUE", "BELOW_VAL")
VALUE_MIGRATIONS = ("VALUE_UP", "VALUE_DOWN", "OVERLAP_FLAT")
PROFILE_SHAPES = ("BALANCED", "UPPER_HEAVY", "LOWER_HEAVY", "UNKNOWN")

PRIMARY_EVENTS = (
    "TEST_VAH_FROM_BELOW",
    "TEST_VAH_FROM_ABOVE",
    "TEST_VAL_FROM_ABOVE",
    "TEST_VAL_FROM_BELOW",
    "POC_TEST",
    "CLOSE_ABOVE_VAH",
    "CLOSE_BELOW_VAL",
    "RETURN_INTO_VALUE_AFTER_ABOVE",
    "RETURN_INTO_VALUE_AFTER_BELOW",
    "HOLD_ABOVE_VAH",
    "HOLD_BELOW_VAL",
    "FULL_VALUE_TRAVERSAL",
    "POC_CROSS_AFTER_OUTSIDE_OPEN",
    "ACCEPTANCE_ABOVE_VAH",
    "ACCEPTANCE_BELOW_VAL",
    "REJECTION_ABOVE_VAH",
    "REJECTION_BELOW_VAL",
)

REPLICATION_LABELS = (
    "REPLICATED_INFORMATION",
    "WEAK_INFORMATION",
    "ERA_DEPENDENT",
    "NO_INFORMATION",
    "REVERSED",
)


@dataclass(frozen=True)
class ReplicationCriteria:
    min_total_n: int = 300
    min_era_n: int = 75
    min_positive_eras: int = 2
    max_era_contribution: float = 0.60
    min_effect_atr: float = 0.03
