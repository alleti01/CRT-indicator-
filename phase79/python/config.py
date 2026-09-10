"""Phase79 — ATM management model test on frozen Phase72A entries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"

PINE_PATH = ROOT.parent / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
EXPECTED_PINE_SHA256 = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
EXPECTED_SIGNAL_HASH = "0da41f282174679f"

# Phase73 M0 baseline (no T5)
BASELINE = {
    "stop_atr": 1.0,
    "target_r": 2.5,
    "max_hold_minutes": 60,
    "collision": "STOP_FIRST",
    "enable_t5": False,
    "one_position": True,
}

# ATM-A default
ATM_A = {
    "stop_r": 1.0,
    "target_r": 2.5,
    "be_trigger_r": 1.0,
    "be_offset_r": 0.05,
    "max_hold_minutes": 60,
    "collision": "STOP_FIRST",
}

# Phase72 independent M0 reproduction anchor (all signals, no one-position filter)
BASELINE_REPRO = {
    "m0_avg_r": 0.01599203459208266,
    "m0_total_r": 578.4958593339982,
    "m0_n": 36174,
    "one_position_n": 35902,
    "one_position_skipped": 272,
}

ROBUSTNESS_BE_TRIGGERS = [0.75, 1.0, 1.25, 1.5]
ROBUSTNESS_BE_OFFSETS = [0.0, 0.05, 0.10]


def pine_sha256() -> str:
    if not PINE_PATH.exists():
        return "MISSING"
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()


def verify_pine_freeze() -> tuple[bool, str]:
    actual = pine_sha256()
    if actual != EXPECTED_PINE_SHA256:
        return False, f"expected {EXPECTED_PINE_SHA256[:16]} got {actual[:16]}"
    return True, actual
