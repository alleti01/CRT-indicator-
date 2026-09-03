"""Phase 44 configuration — frozen simple-score constants from Phase 43 calibration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase44" / "results" / "quality_filtered_pine"

P40_FILTERED = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "filtered_signal_map.csv"
P40_PINE = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "NQ15_COMBINED_PHASE40.pine"
P40_STRATEGY = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "NQ15_COMBINED_PHASE40_STRATEGY.pine"
P43_MANIFEST = ROOT / "phase43" / "results" / "frozen_signal_quality" / "research_manifest.json"

IMPULSE_THRESHOLD = 0.65

# Phase 43 simple-score causal proxy (ret_1_atr + ret_2_atr + ret_3_atr)
# Full-history calibration on N=3791 Phase 40 signals.
Q_RAW_LO = -0.00496580294121185
Q_RAW_HI = 0.02060542475082916
Q_PASS_MIN = 36.49346328963349
Q_TIER_APLUS = 63.198239617422814
Q_TIER_A = 46.076841180646284
Q_TIER_B = 36.49346328963349

# Phase 40 expected counts
EXP_L = 1541
EXP_S = 1345
EXP_RL = 452
EXP_RS = 453
EXP_TOTAL = 3791

# Phase 43 stitched OOS evidence (reference only)
P43_OOS_N = 2788
P43_OOS_AVGR = 0.3499974318258542
P43_OOS_PF = 1.7882353286265988
P43_FILT_N = 1673
P43_FILT_AVGR = 0.5848936616575857
P43_FILT_PF = 2.5115594968604755
