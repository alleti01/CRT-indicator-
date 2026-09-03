"""Phase 40 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase40" / "results" / "impulse_filtered_pine"

P37_SIGNAL_MAP = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "pine_reference_map.csv"
P38_INDICATOR = ROOT / "phase38" / "results" / "concurrent_pine_patch" / "NQ_15M_COMBINED_INDICATOR_CONCURRENT.pine"
P38_STRATEGY = ROOT / "phase38" / "results" / "concurrent_pine_patch" / "NQ_15M_COMBINED_STRATEGY_CONCURRENT.pine"

P40_INDICATOR = RESULTS / "NQ15_COMBINED_PHASE40.pine"
P40_STRATEGY = RESULTS / "NQ15_COMBINED_PHASE40_STRATEGY.pine"

# Phase 37 unfiltered populations
EXP_L = 2075
EXP_S = 1836
EXP_RL = 976
EXP_RS = 925
EXP_TOTAL = EXP_L + EXP_S + EXP_RL + EXP_RS

# Frozen Phase 39 / Phase 40 threshold
IMPULSE_THRESHOLD = 0.65

# Phase 39 reproduction targets (same-method comparison)
P39_FULL_FILTERED_N = 3791
P39_FULL_RETENTION = 0.6522711631108052
P39_OOS_FILTERED_N = 2773
P39_OOS_RETENTION = 0.6499648794193398
P39_FULL_FILTERED_AVGR = 0.3412049296466108
P39_OOS_FILTERED_AVGR = 0.3499974318258542

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
