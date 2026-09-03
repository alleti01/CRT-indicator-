"""Phase57 — NQ Market Sequence & Early-Entry Discovery configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE57_ROOT = ROOT / "phase57"
RESULTS = PHASE57_ROOT / "results"
REPORTS = PHASE57_ROOT / "reports"
TESTS = PHASE57_ROOT / "tests"

TIMEZONE = "America/Chicago"
NQ_TICK = 0.25

# ── Walk-forward folds (identical to Phase53) ──────────────────────────
WALK_FORWARD_FOLDS = (
    ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
)
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-26"

# ── Standardized trade (continuity with S54) ───────────────────────────
STOP_ATR = 0.75
TARGET_R = 2.5
MAX_HOLD_MIN = 60

# Robustness grid (small, predeclared — NOT permission to mine)
STOP_ATR_GRID = (0.5, 0.75, 1.0)
TARGET_R_GRID = (2.0, 2.5, 3.0)
COST_MULTIPLIERS = (1.0, 1.5, 2.0)

# ── Swing / structure ──────────────────────────────────────────────────
DEFAULT_SWING = 5
DISPLACEMENT_BODY_MULT = 1.5

# ── ORB ────────────────────────────────────────────────────────────────
CASH_OPEN_CT = "08:30"
ORB_WINDOWS_MIN = (5, 15, 30)

# ── FVG ────────────────────────────────────────────────────────────────
FVG_TIMEFRAMES = ("1M", "5M", "15M")

# ── Outcome horizons ──────────────────────────────────────────────────
OUTCOME_HORIZONS = (5, 10, 15, 30, 60)

# ── Warmup ─────────────────────────────────────────────────────────────
WARMUP_BARS = 500

# ── Frozen S54 reference (read-only) ──────────────────────────────────
S54_MODEL_HASH = "bccf4277f3d44d13"
PHASE55_FROZEN = ROOT / "phase55" / "frozen"
P54_SCORED_CACHE = ROOT / "phase54" / "results" / "episode_consolidation" / "scored_prehold.parquet"
PHASE53_PARQUET = ROOT / "phase53" / "results" / "opportunity_discovery" / "event_dataset.parquet"

# ── Entry stages ──────────────────────────────────────────────────────
ENTRY_STAGES = ("E0", "E1", "E2", "E3", "E4")
MAX_DECISION_BARS = 3

# ── Session buckets (CT) ─────────────────────────────────────────────
SESSION_BUCKETS = {
    "pre_cash_open": ("00:00", "08:30"),
    "08:30-09:00": ("08:30", "09:00"),
    "09:00-10:00": ("09:00", "10:00"),
    "10:00-11:30": ("10:00", "11:30"),
    "11:30-13:00": ("11:30", "13:00"),
    "13:00-14:00": ("13:00", "14:00"),
    "14:00-15:00": ("14:00", "15:00"),
}
