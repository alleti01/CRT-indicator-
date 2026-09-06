"""Randomized direction control gate — Families A–F, preregistered thresholds."""
from __future__ import annotations

# Preregistered gate thresholds — NOT tuned from results.
RANDOM_SEED_COUNT = 100
RANDOM_SEED_START = 76001

# Timestamp-shift placebo (bars forward on entry index — fixed, not optimized)
TIMESTAMP_SHIFT_BARS = (5, 15, 30)

# Effect-size gates (practical, not p-value only)
MIN_EFFECT_FP11 = 0.012  # real minus random mean on P(+1 before -1)
MIN_EFFECT_FP21 = 0.012
MIN_PERCENTILE_STRONG = 85
MIN_PERCENTILE_WEAK = 70
INVERSE_MARGIN_FP21 = 0.015  # flip exceeds real → INVERSE_INFORMATION
STRONG_ASYM_15 = 1.025
WEAK_ASYM_15 = 1.010
MIN_N_FAMILY = 200  # below → DATA_INSUFFICIENT for gate
