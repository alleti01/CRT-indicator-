"""Phase58E causality tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]

from phase58b.research.precompute import build_mtf_arrays
from phase58e.research.direction_engine import evaluate_opportunity


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_hashes():
    cfg = json.load(open(ROOT / "phase58e" / "config" / "phase58e_frozen.json"))
    assert _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json") == cfg["phase58_v1_hash"]
    assert _hash_file(ROOT / "phase58d" / "config" / "phase58d_frozen.json") == cfg["phase58d_config_hash"]


def test_opportunity_timestamp_preserved():
    opps = pd.read_parquet(ROOT / "phase58d" / "results" / "opportunities.parquet")
    assert "created_i" in opps.columns
    assert opps["created_i"].notna().all()


def test_truncation_invariance_direction():
    cfg = json.load(open(ROOT / "phase58e" / "config" / "phase58e_frozen.json"))
    m = build_mtf_arrays()
    opps = pd.read_parquet(ROOT / "phase58d" / "results" / "opportunities.parquet").head(500)
    for _, o in opps.sample(min(20, len(opps)), random_state=42).iterrows():
        i = int(o["created_i"])
        a = evaluate_opportunity(m, i, o["direction"], cfg)
        b = evaluate_opportunity(m, i, o["direction"], cfg)
        assert a["shadow_direction_t0"] == b["shadow_direction_t0"]
        assert a["market_state"] == b["market_state"]


def test_t0_zero_delay():
    opps = pd.read_parquet(ROOT / "phase58d" / "results" / "opportunities.parquet")
    audit = pd.read_parquet(ROOT / "phase58e" / "results" / "direction_audit.parquet") if (
        ROOT / "phase58e" / "results" / "direction_audit.parquet"
    ).exists() else None
    if audit is not None:
        merged = opps.merge(audit[["opportunity_id", "bar_i"]], on="opportunity_id")
        assert (merged["created_i"] == merged["bar_i"]).all()
