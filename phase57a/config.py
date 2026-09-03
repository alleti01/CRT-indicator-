"""Phase57A — Adversarial Audit configuration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PHASE57A_ROOT = ROOT / "phase57a"
RESULTS = PHASE57A_ROOT / "results"
REPORTS = PHASE57A_ROOT / "reports"

PHASE57_ROOT = ROOT / "phase57"
PHASE55_FROZEN = ROOT / "phase55" / "frozen"
S54_MODEL_HASH = "bccf4277f3d44d13"

FROZEN_PHASE57_CONFIG = {
    "leg_min_distance_atr": 1.0,
    "leg_swing": 5,
    "leg_start_i": 100,
    "pullback_min_depth_pct": 0.15,
    "pullback_max_depth_pct": 1.0,
    "pullback_max_bars": 60,
    "sequence_max_reaction_bars": 5,
    "stop_atr": 0.75,
    "target_r": 2.5,
    "max_hold_min": 60,
    "cost_mult": 1.0,
    "warmup_bars": 500,
    "holdout_start": "2025-01-01",
    "holdout_end": "2026-06-26",
    "wf_folds": [
        ("2018-01-01", "2019-12-31", "2020-01-01", "2020-12-31"),
        ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("2018-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    ],
}

PHASE57_CONFIG_HASH = hashlib.sha256(
    json.dumps(FROZEN_PHASE57_CONFIG, sort_keys=True).encode()
).hexdigest()[:16]

TRUNCATION_SAMPLE_SIZE = 5000
TRACE_SAMPLE_SIZE = 25
