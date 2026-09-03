"""Phase 38 — concurrent reversal Pine patch configuration."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "phase38" / "results" / "concurrent_pine_patch"

# Authoritative Phase 37 reference
P37_REFERENCE_MAP = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "pine_reference_map.csv"
P37_MANIFEST = ROOT / "phase37" / "results" / "concurrent_reversal_parity" / "research_manifest.json"
P36_SIGNAL_MAP = ROOT / "phase36" / "results" / "full_history_signal_replay" / "full_history_signal_map.csv"

# Expected counts (Phase 37 validated)
EXP_CONT_L = 2075
EXP_CONT_S = 1836
EXP_REV_RL = 976
EXP_REV_RS = 925
EXP_REV_TOTAL = 1901
EXP_RESTORED = 684
EXP_PINE_POOL_CAP = 8
EXP_MAX_CONCURRENT = 5

CONFLICT_POLICY = "INDEPENDENT"
