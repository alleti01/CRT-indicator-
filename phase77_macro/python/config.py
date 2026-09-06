"""Phase77-MACRO configuration — observation universe only, framework frozen."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE77_MACRO = ROOT / "phase77_macro"
PHASE77 = ROOT / "phase77"
DATA_DIR = PHASE77_MACRO / "data"
REPORTS = PHASE77_MACRO / "reports"
CHECKPOINTS = PHASE77_MACRO / "checkpoints"
DIAGNOSTICS = PHASE77_MACRO / "diagnostics"

# Frozen macro windows (minutes) — not optimized
MACRO_PRE_MINUTES = 15
MACRO_POST_MINUTES = 60

SUBWINDOWS = (
    ("PRE", -15, 0),
    ("IMMEDIATE", 0, 5),
    ("EARLY", 5, 15),
    ("DEVELOPMENT", 15, 30),
    ("LATE", 30, 60),
)

TIMEZONE_UTC = "UTC"
TIMEZONE_NY = "America/New_York"
TIMEZONE_CHI = "America/Chicago"

# Sample size gates
N_TOO_SMALL = 30
N_EXPLORATORY = 100

# Same-time control matching
MAX_SMD_ACCEPT = 0.10
MATCH_SEED = 77101

# Random direction (same seeds as Phase77)
RANDOM_SEED_COUNT = 100
RANDOM_SEED_START = 77001
MIN_EFFECT_FP11 = 0.015

# Phase77 files that must match freeze manifest
FREEZE_FILES = (
    "phase77/python/config.py",
    "phase77/python/framework_layers.py",
    "phase77/python/setups.py",
    "phase77/python/gates.py",
    "phase77/python/trade_vap_profile.py",
)

CALENDAR_PATH = DATA_DIR / "tier1_macro_calendar_jan2024.json"
