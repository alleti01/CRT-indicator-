"""Phase 45 configuration — frozen strategy constants and benchmarks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase45" / "results" / "forward_validation"

# Frozen references
P44_RESULTS = ROOT / "phase44" / "results" / "quality_filtered_pine"
P44B_RESULTS = ROOT / "phase44b" / "results" / "final_quality_validation"
P40_FILTERED = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "filtered_signal_map.csv"

# Dataset classification
DATASET_TAG = "FORWARD_VALIDATION_ONLY"

# Frozen Phase 40 impulse
IMPULSE_THRESHOLD = 0.65

# Frozen Phase 44 quality score (DO NOT RECALIBRATE) — exact Phase 44 constants
Q_RAW_LO = -0.00496580294121185
Q_RAW_HI = 0.02060542475082916
Q_RAW_SPAN = Q_RAW_HI - Q_RAW_LO
Q_PASS_MIN = 36.49346328963349
Q_TIER_APLUS = 63.198239617422814
Q_TIER_A = 46.076841180646284
Q_TIER_B = 36.49346328963349

# Max hold minutes (frozen)
MAX_HOLD_CONTINUATION_MIN = 60
MAX_HOLD_REVERSAL_MIN = 45

# Validation checkpoints (accepted trades)
CHECKPOINTS = (25, 50, 100, 200, 300, 500)
PRIMARY_CHECKPOINTS = (100, 200, 300, 500)
ROLLING_WINDOWS = (20, 50, 100)

# Phase 44B research benchmarks (comparison only)
BENCHMARK_BASELINE = {"N": 2788, "AvgR": 0.350, "PF": 1.79}
BENCHMARK_FILTERED = {"N": 1750, "AvgR": 0.566, "PF": 2.44}
BENCHMARK_REJECTED = {"N": 1038, "AvgR": -0.015, "PF": 0.97}
BENCHMARK_TIERS = {"A+": 0.830, "A": 0.460, "B": 0.373}

# Drift warning thresholds (diagnostic only)
DRIFT_WARN_PF = 1.0
DRIFT_WARN_AVGR = 0.0

RTH_SESSION = "0930-1600"
