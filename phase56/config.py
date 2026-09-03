"""Phase56 — S54 forward paper validation configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE56_ROOT = ROOT / "phase56"
FROZEN = PHASE56_ROOT / "frozen"
LOGS = PHASE56_ROOT / "logs"
STATE = PHASE56_ROOT / "state"
REPORTS = PHASE56_ROOT / "reports"
RESULTS = PHASE56_ROOT / "results"
TESTS = PHASE56_ROOT / "tests"
FORWARD = PHASE56_ROOT / "forward"

# Immutable forward sample boundary (America/Chicago)
FORWARD_START_TIMESTAMP_CT = "2025-01-01 00:00:00"
FREEZE_TIMESTAMP_CT = "2026-08-28 00:00:00"  # Phase55 sequential freeze
MODEL_HASH = "bccf4277f3d44d13"
TIMEZONE = "America/Chicago"

# Forward scoring: fold 5 is the most recent frozen model (train through 2023, no holdout leakage)
FORWARD_SCORING_FOLD = 5

# Historical OOS benchmarks (Phase54 reference)
HISTORICAL_OOS = {
    "N": 10_587,
    "episodes_day": 7.271291208791209,
    "AvgR": 0.8294948177072894,
    "PF": 2.6499530084335507,
    "TotalR": 8781.861635067073,
    "MaxDD": 126.009088598169,
    "LONG_AvgR": 0.865,
    "SHORT_AvgR": 0.783,
    "CORE_unauth_AvgR": 0.8231322210329965,
    "cost2x_AvgR": 0.633,
    "holdout_AvgR": 0.939,
    "holdout_PF": 3.05,
    "d10_events_day": 29.7,
    "episode_reduction_pct": 75.6,
}

CHECKPOINTS = (25, 50, 100, 200)
PRIMARY_CHECKPOINT = 100
STRONG_CHECKPOINT = 200

# Phase55 paths (read-only)
PHASE55_FROZEN = ROOT / "phase55" / "frozen"
PHASE55_IMPLEMENTATION = ROOT / "phase55" / "implementation"
P54_SCORED_CACHE = ROOT / "phase54" / "results" / "episode_consolidation" / "scored_prehold.parquet"

from phase53.config import HOLDOUT_END, MAX_HOLD_MIN, STOP_ATR, TARGET_R  # noqa: E402
from phase55.config import WARMUP_BARS  # noqa: E402
