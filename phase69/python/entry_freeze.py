"""Phase69 — frozen canonical entry stream."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CANON = ROOT / "phase60" / "diagnostics" / "cache" / "canon_full_phase60.parquet"
CONFIG = ROOT / "phase59" / "config" / "phase59_frozen_config.json"

ENTRY_SPEC = {
    "pipeline": "Phase58D variant E → Phase58F P4 → Phase58H H1 KEEP → M1 entry",
    "signal_source": "phase60/diagnostics/cache/canon_full_phase60.parquet",
    "pine_reference": "TV_REVIEW/phase59_canonical_live.pine",
    "entry": "signal bar close T → entry next 1M open T+1",
    "direction": "direction_m1 from canonical pipeline",
    "atr": "SMA(14) of range on 1M",
    "m0_stop_atr": 1.0,
    "m0_target_r": 2.5,
    "m0_max_hold_min": 60,
    "collision": "STOP_FIRST",
    "cost": "NQ round-turn $14.50 normalized to R",
}


def config_hash() -> str:
    raw = CONFIG.read_text() + json.dumps(ENTRY_SPEC, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_frozen_entries() -> pd.DataFrame:
    df = pd.read_parquet(CANON)
    df = df.loc[df["h1_status"] == "KEEP"].copy()
    df["direction"] = df["direction_m1"]
    df["entry_i"] = df["entry_i_m1"].astype(int)
    df["entry_price"] = df["entry_price_m1"].astype(float)
    df["signal_i"] = df["signal_m1_i"].astype(int)
    df["atr_entry"] = df["atr"].astype(float)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    return df.sort_values("entry_ts").reset_index(drop=True)


def executions(df: pd.DataFrame) -> pd.DataFrame:
    return df[["trade_id", "setup_id", "direction", "signal_i", "entry_i", "entry_price", "atr_entry", "entry_ts"]].copy()
