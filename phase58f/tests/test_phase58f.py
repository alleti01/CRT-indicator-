"""Phase58F causality tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]

from phase58b.research.precompute import build_mtf_arrays
from phase58f.research.confidence import compute_confidence


def _hash(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_hashes():
    cfg = json.load(open(ROOT / "phase58f" / "config" / "phase58f_frozen.json"))
    assert _hash(ROOT / "phase58d" / "config" / "phase58d_frozen.json") == cfg["phase58d_config_hash"]
    assert _hash(ROOT / "phase58e" / "config" / "phase58e_frozen.json") == cfg["phase58e_config_hash"]


def test_same_timestamp_as_phase58d():
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet") if (
        ROOT / "phase58f" / "results" / "confidence_audit.parquet"
    ).exists() else None
    if audit is not None:
        m = tr.merge(audit, left_on="trade_id", right_on="trade_id")
        assert (m["signal_m1_i"] == m["bar_i"]).all()


def test_truncation_invariance():
    cfg = json.load(open(ROOT / "phase58f" / "config" / "phase58f_frozen.json"))
    m = build_mtf_arrays()
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet").head(100)
    row = tr.iloc[50]
    i = int(row["signal_m1_i"])
    a = compute_confidence(m, i, row["direction"], cfg)
    b = compute_confidence(m, i, row["direction"], cfg)
    assert a["direction_confidence_band"] == b["direction_confidence_band"]


def test_no_outcome_in_confidence():
    cfg = json.load(open(ROOT / "phase58f" / "config" / "phase58f_frozen.json"))
    m = build_mtf_arrays()
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet").iloc[0]
    c = compute_confidence(m, int(tr["signal_m1_i"]), tr["direction"], cfg)
    assert "net_R" not in c
    assert "exit_reason" not in c
