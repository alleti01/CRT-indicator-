"""Phase78B paths and constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHASE78B = ROOT / "phase78b"
REPORTS = PHASE78B / "reports"
CHECKPOINTS = PHASE78B / "checkpoints"
DATA = PHASE78B / "data"

PHASE78_ROOT = ROOT / "phase78"
PHASE78_REPORTS = PHASE78_ROOT / "reports"

FREEZE_FILES = (
    "python/config.py",
    "python/liquidity.py",
    "python/sequence.py",
    "python/swings.py",
    "python/session_cache.py",
    "python/windows.py",
    "python/paths.py",
)

MIN_SOURCE_N = 100
MIN_EFFECT = 0.012
