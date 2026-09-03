"""Phase 44B configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase44b" / "results" / "final_quality_validation"

# Rejection region (frozen from Phase 43/44 — bottom 40%)
REJECT_BOTTOM_PCT = 0.40
RTH_SESSION = "0930-1600"

# Fixed Phase 44 Pine constants (reference only, not OOS evidence)
FIXED_Q_RAW_LO = -0.00496580294121185
FIXED_Q_RAW_HI = 0.02060542475082916
FIXED_Q_PASS_MIN = 36.49346328963349
FIXED_Q_TIER_APLUS = 63.198239617422814
FIXED_Q_TIER_A = 46.076841180646284
FIXED_Q_TIER_B = 36.49346328963349

EXP_TOTAL = 3791
MC_SIMS = 10000
BOOTSTRAP_SIMS = 10000

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
