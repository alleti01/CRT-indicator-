"""Phase58I tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_integrity():
    cfg = json.load(open(ROOT / "phase58i" / "config" / "phase58i_frozen.json"))
    assert _hash_file(ROOT / "phase58h" / "config" / "phase58h_frozen.json") == cfg["phase58h_config_hash"]


def test_h1_parity():
    from phase58i.research.canonical import canonical_trades
    from phase58b.research.simulation import metrics

    canon = canonical_trades("H1")
    assert len(canon) == 60118
    m = metrics(canon["net_R"].values)
    assert abs(m["TotalR"] - 11581.43) < 10


def test_m0_unchanged():
    from phase58i.research.canonical import canonical_trades
    from phase58i.research.management import simulate_management, executions_from_trades
    from phase58b.research.precompute import build_mtf_arrays

    canon = canonical_trades("H1").head(100)
    m = build_mtf_arrays()
    cfg = json.load(open(ROOT / "phase58i" / "config" / "phase58i_frozen.json"))
    cfg.update(json.load(open(ROOT / "phase58d" / "config" / "phase58d_frozen.json")))
    ex = executions_from_trades(canon)
    sim = simulate_management(m, ex, cfg, "M0")
    assert len(sim) == len(canon)
    assert abs(sim["net_R"].sum() - canon["net_R"].sum()) < 1.0
