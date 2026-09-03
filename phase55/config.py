"""Phase55 — S54 implementation/parity configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE55_ROOT = ROOT / "phase55"
FROZEN = PHASE55_ROOT / "frozen"
REFERENCE = PHASE55_ROOT / "reference"
RESULTS = PHASE55_ROOT / "results"
IMPLEMENTATION = PHASE55_ROOT / "implementation"

PHASE53_PARQUET = ROOT / "phase53" / "results" / "opportunity_discovery" / "event_dataset.parquet"
P54_SCORED_CACHE = ROOT / "phase54" / "results" / "episode_consolidation" / "scored_prehold.parquet"
P54_SEL_CACHE = ROOT / "phase54" / "results" / "episode_consolidation" / "score_selection.json"

from phase53.config import (  # noqa: E402
    DEFAULT_SWING,
    DISPLACEMENT_BODY_MULT,
    HOLDOUT_END,
    HOLDOUT_START,
    MAX_HOLD_MIN,
    STOP_ATR,
    TARGET_R,
    WALK_FORWARD_FOLDS,
)
from phase54.config import P53_REF  # noqa: E402

# Frozen S54 specification
S54_EPISODE_FAMILY = "A"
S54_TIME_WINDOW_MIN = 30
S54_ENTRY_RULE = "FIRST_QUALIFYING_EVENT"

# Phase54 WF OOS reference (parity targets)
P54_REF = {
    "episodes_n": 10_587,
    "episodes_day": 7.271291208791209,
    "avgr": 0.8294948177072894,
    "pf": 2.6499530084335507,
    "totalr": 8781.861635067073,
    "maxdd": 126.009088598169,
    "unauth_avgr": 0.8231322210329965,
    "unauth_pf": 2.6303139776235045,
}

# Parity tolerances
EVENT_COUNT_TOL = 0
EVENT_TS_EXACT = True
FEATURE_MAE_TOL = 1e-6
SCORE_MAE_TOL = 1e-8
PRICE_TICK_TOL = 0.0
D10_AGREEMENT_MIN = 0.9999
EPISODE_MATCH_MIN = 0.999
PERF_AVGR_TOL = 0.001

WARMUP_BARS = 500
RESTART_WARMUP_BARS = 600
