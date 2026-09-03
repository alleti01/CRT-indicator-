"""Phase54 — opportunity episode consolidation configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE54_ROOT = ROOT / "phase54"
RESULTS = PHASE54_ROOT / "results" / "episode_consolidation"

PHASE53_PARQUET = ROOT / "phase53" / "results" / "opportunity_discovery" / "event_dataset.parquet"
PHASE53_SCORE_DECILES = ROOT / "phase53" / "results" / "opportunity_discovery" / "score_deciles.csv"

# Reuse Phase53 frozen settings
from phase53.config import (  # noqa: E402
    CORE_BENCHMARK,
    HOLDOUT_END,
    HOLDOUT_START,
    WALK_FORWARD_FOLDS,
)

CORE_OVERLAP_MIN = 30

# Phase53 parity tolerances
PARITY_TOL_EVENTS = 0.001
PARITY_TOL_AVGR = 0.05
PARITY_TOL_D10_N = 0.02

# Consolidation grids (small, predeclared)
TIME_WINDOWS = (5, 10, 15, 20, 30)
ATR_SEPARATIONS = (0.5, 1.0, 1.5)
STRUCT_SWING_RESET = (3, 5)  # bars lookback for opposite BOS proxy

# Phase53 reference (from Phase53 report)
P53_REF = {
    "total_events": 925_486,
    "scored_oos_n": 542_462,
    "d10_n": 54_247,
    "d10_avgr": 0.8139497113561064,
    "d10_unauth_avgr": 0.8076213578383081,
    "top20_n": 108_493,
    "top20_avgr": 0.6134566303895433,
    "top20_epd": 59.44821917808219,
    "d10_epd": 29.740679824561404,
}

SEARCH_MANIFEST = {
    "consolidation_families": ("E0", "A", "B", "C", "D", "E", "F"),
    "time_windows": TIME_WINDOWS,
    "atr_separations": ATR_SEPARATIONS,
}
