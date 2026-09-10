"""Phase80 configuration and freeze constants."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"

PINE_PATH = ROOT.parent / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
CANON_PARQUET = ROOT.parent / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"

EXPECTED_PINE_SHA256 = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
EXPECTED_SIGNAL_HASH = "0da41f282174679f"
BASELINE_AVG_R = 0.015992034592082663
BASELINE_N = 36174

M0 = {
    "stop_r": 1.0,
    "target_r": 2.5,
    "max_hold_minutes": 60,
    "collision": "STOP_FIRST",
}

TRAIN_FRAC = 0.6
VALID_FRAC = 0.8
MIN_FULL_N = 1000
MIN_VAL_N = 200
MAX_FINALISTS = 10
PREFIX_SAMPLE_N = 500


def pine_sha256() -> str:
    if not PINE_PATH.exists():
        return "MISSING"
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()
