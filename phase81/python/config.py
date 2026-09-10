"""Phase81 configuration."""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
CHECKPOINTS = ROOT / "checkpoints"

PINE_PATH = ROOT.parent / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
CANON_PARQUET = ROOT.parent / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"

EXPECTED_PINE_SHA256 = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
EXPECTED_SIGNAL_HASH = "0da41f282174679f"

TRAIN_FRAC = 0.6
VALID_FRAC = 0.8
MIN_SHORT_FULL = 500
MIN_SHORT_VAL = 150
MIN_RETENTION_PCT = 30.0
MAX_FINALISTS = 10

M0 = {"stop_r": 1.0, "target_r": 2.5, "max_hold_minutes": 60, "collision": "STOP_FIRST"}


def pine_sha256() -> str:
    if not PINE_PATH.exists():
        return "MISSING"
    return hashlib.sha256(PINE_PATH.read_bytes()).hexdigest()


def long_stream_hash(long_df) -> str:
    import pandas as pd

    ids = long_df.sort_values("entry_ts")[["trade_id", "entry_ts", "direction_m1"]]
    payload = ids.to_csv(index=False).encode()
    return hashlib.sha256(payload).hexdigest()[:16]
