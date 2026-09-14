"""Phase84 — Phase72A price-action execution quality research configuration."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"
DATA = ROOT / "data"

PINE_PATH = REPO / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
EXPECTED_PINE_SHA256 = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"

# M0 authority (Phase73 production path)
M0_REFERENCE_PATH = "phase73/trader/management.py"
M0_REFERENCE_FUNCTIONS = ("build_management", "evaluate_exit")
M0_STOP_ATR = 1.0
M0_TARGET_R = 2.5
M0_MAX_HOLD_MIN = 60
M0_COLLISION = "STOP_FIRST"

# Chronological splits
TRAIN_FRAC = 0.60
VALID_FRAC = 0.80  # train end; valid = [0.6, 0.8); test = [0.8, 1.0)

# Sample gates
MIN_FULL = 500
MIN_VAL = 150
MIN_TEST = 150
MIN_RETENTION_PCT = 30.0
PREFERRED_RETENTION_PCT = 50.0

# Coarse grids (predeclared)
RANGE_WINDOWS = (10, 20, 30)
WAIT_BARS = (1, 2, 3)
BODY_FRAC_THRESHOLDS = (0.4, 0.55, 0.7)
EXT_ATR_BUCKETS = (0.5, 1.0, 1.5, 2.0)

# Costs (NQ round-turn baseline + stress)
COST_MULTS = (1.0, 1.5, 2.0)
TICK_SLIPPAGE = (0, 1, 2)
NQ_TICK = 0.25

# Signal source paths (priority order in loader)
WEBHOOK_CSV = REPO / "forward_rehearsal" / "reports" / "WEBHOOK_ALERTS_FULL.csv"
TV_EXPORT_PATH = DATA / "phase72a_tv_export.csv"
LEDGER_EXPORT_PATH = DATA / "phase72a_ledger_export.csv"
PROVISIONAL_MIRROR_FLAG = False  # must stay False unless explicitly enabled for dev

# Opportunity deduplication
OPPORTUNITY_GAP_BARS = 30

# Causality audit
CAUSALITY_SAMPLE = 500

# Outcome horizons (labels only)
OUTCOME_HORIZONS = (5, 10, 15, 30, 60)


def pine_sha256() -> str:
    if not PINE_PATH.exists():
        return "MISSING"
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()


def m0_reference_hash() -> str:
    p = REPO / M0_REFERENCE_PATH
    if not p.exists():
        return "MISSING"
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]
