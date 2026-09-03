"""Phase53 — event-level opportunity discovery configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE53_ROOT = ROOT / "phase53"
RESULTS = PHASE53_ROOT / "results" / "opportunity_discovery"

TIMEZONE = "America/Chicago"
RTH_SESSION = "0930-1600"
NQ_TICK = 0.25
DEFAULT_SWING = 5
DISPLACEMENT_BODY_MULT = 1.5

# Frozen standardized research trade (Phase52)
STOP_ATR = 0.75
TARGET_R = 2.5
MAX_HOLD_MIN = 60

P44_SIGNALS = ROOT / "phase44" / "results" / "quality_filtered_pine" / "quality_reference_all_signals.csv"
P45_WF = ROOT / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv"

# Walk-forward (model selection — excludes holdout)
WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
)

# Final holdout — never used for feature/model/threshold selection
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-26"

# Predeclared opportunity labels (outcome only)
OPPORTUNITY_DEFS = (
    {"name": "O1", "mfe_atr": 1.0, "mae_atr": 0.5, "horizon_min": 30},
    {"name": "O2", "mfe_atr": 1.5, "mae_atr": 0.75, "horizon_min": 60},
    {"name": "O3", "mfe_atr": 2.0, "mae_atr": 1.0, "horizon_min": 60},
    {"name": "O4", "mfe_r": 2.5, "mae_r": 1.0, "horizon_min": 60, "use_r": True},
)

OUTCOME_HORIZONS = (5, 10, 15, 30, 60)
RANGE_WINDOWS_15M = (4, 8, 12, 20)
RANGE_WINDOWS_5M = (4, 8, 12)

EVENT_TYPES = tuple(f"E{i}" for i in range(1, 17))

CORE_BENCHMARK = {"N": 1135, "AvgR": 1.648, "PF": 17.78, "MaxDD": 8.39}
B1_WINDOW_MIN = 10
CORE_OVERLAP_MIN = 30

# Model feature caps for constrained models
FEATURE_COUNTS = (3, 5, 8, 12)

# Multiple-testing manifest counters (updated at runtime)
SEARCH_SPACE = {
    "event_types": 16,
    "features_examined": 0,
    "models_tested": 0,
    "hyperparameter_combos": 0,
}
