"""Phase82 configuration — 15M context → 1M execution (NO 5M)."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"

PINE_PATH = ROOT.parent / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
CANON_PARQUET = ROOT.parent / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"

EXPECTED_PINE_SHA256 = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
EXPECTED_STREAM_HASH = "0da41f282174679f"
EXPECTED_N = 36174
BASELINE_AVG_R = 0.015992034592082663

TRAIN_FRAC = 0.6
VALID_FRAC = 0.8
MIN_FULL = 1000
MIN_VAL = 250
MIN_TEST = 250
MIN_SIDE_VAL = 150
MIN_RETENTION = 40.0
MIN_SHORT_RETENTION = 30.0
MIN_LONG_RETENTION = 50.0

M0 = {"stop_r": 1.0, "target_r": 2.5, "max_hold_minutes": 60, "collision": "STOP_FIRST"}

# Coarse thresholds (not optimized)
EXT_ATR = 1.0
PULLBACK_ATR = 0.35
COMMIT_BODY_ATR = 0.4
WAIT_MAX_BARS = 30

MODEL_IDS = [f"P{i}" for i in range(11)]


def pine_sha256() -> str:
    if not PINE_PATH.exists():
        return "MISSING"
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()
