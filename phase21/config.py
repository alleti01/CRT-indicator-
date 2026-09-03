"""Phase 21 preregistered discovery parameters."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase21" / "results" / "volatility_state_edge"

# Predefined bar horizons (5-minute bars).
SHORT_BARS = 6
MEDIUM_BARS = 24
LONG_BARS = 72
HORIZONS = (1, 3, 6, 12, 24)

# Rolling percentile window: 60 CME session days ≈ 16,800 five-minute bars.
PERCENTILE_WINDOW_BARS = 16_800
PERCENTILE_MIN_PERIODS = 5_000
LOW_PERCENTILE = 0.20
HIGH_PERCENTILE = 0.80

COMPRESSION_DURATION_BINS = (
    "1-3",
    "4-6",
    "7-12",
    "13-24",
    "25+",
)

SHOCK_PERCENTILE_BINS = (
    "<80",
    "80-90",
    "90-95",
    "95-99",
    "99+",
)

VOL_MEASURES = (
    "ATR_RATIO",
    "RV_RATIO",
    "RANGE_RATIO",
    "ATR_24",
)

PRIMARY_STATE_MEASURE = "ATR_24"

REGIME_TRANSITIONS = (
    "LOW->NORMAL",
    "LOW->HIGH",
    "NORMAL->HIGH",
    "NORMAL->LOW",
    "HIGH->NORMAL",
    "HIGH->LOW",
    "LOW->LOW",
    "NORMAL->NORMAL",
    "HIGH->HIGH",
)

EXPANSION_TRANSITIONS = ("LOW->NORMAL", "LOW->HIGH")

# Minimum completed bars in prior state before a transition event fires (anti-flicker).
MIN_PRIOR_STATE_BARS = 6

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

TIME_BUCKETS: Dict[str, Tuple[int, int]] = {
    "OVERNIGHT": (18 * 60, 4 * 60),
    "PREMARKET": (4 * 60, 9 * 60 + 30),
    "RTH_OPEN": (9 * 60 + 30, 10 * 60 + 30),
    "RTH_MID_MORNING": (10 * 60 + 30, 12 * 60),
    "MIDDAY": (12 * 60, 14 * 60),
    "RTH_AFTERNOON": (14 * 60, 16 * 60),
}


@dataclass(frozen=True)
class DirectionalReplication:
    min_total_n: int = 300
    min_era_n: int = 75
    min_positive_eras: int = 2
    max_era_contribution: float = 0.60
    min_effect_atr: float = 0.03


@dataclass(frozen=True)
class MagnitudeReplication:
    min_total_n: int = 300
    min_era_n: int = 75
    min_uplift_pct: float = 5.0
    max_era_contribution: float = 0.60
