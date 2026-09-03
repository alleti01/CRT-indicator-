"""Phase 43 configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase43" / "results" / "frozen_signal_quality"

P40_FILTERED = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "filtered_signal_map.csv"
P40_MANIFEST = ROOT / "phase40" / "results" / "impulse_filtered_pine" / "research_manifest.json"

IMPULSE_THRESHOLD = 0.65

# Expected Phase 40 filtered counts
EXP_L = 1541
EXP_S = 1345
EXP_RL = 452
EXP_RS = 453
EXP_TOTAL = 3791

# Expected baseline economics (full history, net)
EXP_AVGR = 0.3412049296466108
EXP_PF = 1.7529123260601682
EXP_N = 3791

# OOS stitched baseline
EXP_OOS_N = 2788
EXP_OOS_AVGR = 0.3499974318258542

# Success gates
MIN_FILTER_N = 500
MIN_AVGR_IMPROVEMENT = 0.05
MIN_PF_IMPROVEMENT = 0.10
MIN_FILTERED_PF = 1.50

RETENTION_LEVELS = (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1)
REJECTION_RATES = (0.10, 0.20, 0.30, 0.40)
HIGH_CONF_LEVELS = (0.50, 0.70, 0.80, 0.90, 0.95)

MC_SIMS = 10000
BOOTSTRAP_SIMS = 5000

from phase29.config import WALK_FORWARD_FOLDS  # noqa: E402
