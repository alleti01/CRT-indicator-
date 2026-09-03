"""Phase 23 preregistered discovery parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase23" / "results" / "directional_displacement_edge"

HORIZONS = (1, 3, 6, 12, 24)
ATR_PRIMARY = 24
ATR_DIAG = (6, 72)
STRUCTURE_LOOKBACK = 12
DEDUP_SAME_DIRECTION_BARS = 3

BODY_ATR_THRESHOLDS = (0.50, 0.75, 1.00, 1.25, 1.50)
BODY_ATR_BUCKETS = ("<0.50", "0.50-0.75", "0.75-1.00", "1.00-1.25", "1.25-1.50", ">=1.50")
PERCENTILE_THRESHOLDS = (0.90, 0.95, 0.99)
MIN_BODY_ATR_EVENT = 0.50

PERCENTILE_WINDOW_BARS = 16_800
PERCENTILE_MIN_PERIODS = 5_000
VOLUME_MEDIAN_BARS = 24

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

SESSION_BUCKETS: Dict[str, Tuple[int, int]] = {
    "OVERNIGHT": (18 * 60, 4 * 60),
    "PREMARKET": (4 * 60, 9 * 60 + 30),
    "RTH_OPEN": (9 * 60 + 30, 10 * 60 + 30),
    "RTH_MORNING": (10 * 60 + 30, 12 * 60),
    "RTH_MIDDAY": (12 * 60, 14 * 60),
    "RTH_AFTERNOON": (14 * 60, 16 * 60),
}

REPLICATION_LABELS = (
    "REPLICATED_DIRECTIONAL_EDGE",
    "WEAK_DIRECTIONAL_INFORMATION",
    "ERA_DEPENDENT",
    "SESSION_DEPENDENT",
    "NO_DIRECTIONAL_INFORMATION",
    "REVERSAL_INFORMATION",
    "INSUFFICIENT_SAMPLE",
)

MONOTONICITY_LABELS = (
    "MONOTONIC_CONTINUATION",
    "MONOTONIC_REVERSAL",
    "NON_MONOTONIC",
    "NO_RELATIONSHIP",
)

EFFECT_BANDS = (
    (0.05, "NEGLIGIBLE"),
    (0.10, "SMALL"),
    (0.20, "INTERESTING"),
    (0.30, "STRONG"),
    (float("inf"), "VERY_STRONG"),
)


@dataclass(frozen=True)
class ReplicationCriteria:
    min_total_n: int = 500
    min_era_n: int = 100
    min_positive_eras: int = 2
    max_era_contribution: float = 0.60
    min_effect_atr: float = 0.05
