"""Phase58C causality tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from phase58c.research.clustering import cluster_1m_opportunities


@pytest.fixture
def cfg():
    return json.load(open(ROOT / "config" / "phase58c_frozen.json"))


def test_phase58_hash(cfg):
    p58 = json.load(open(ROOT.parent / "phase58" / "config" / "phase58_v1_frozen.json"))
    h = hashlib.sha256(json.dumps(p58, sort_keys=True).encode()).hexdigest()[:16]
    assert h == cfg["phase58_v1_hash"]


def test_phase58b_hash(cfg):
    p58b = json.load(open(ROOT.parent / "phase58b" / "config" / "phase58b_frozen.json"))
    h = hashlib.sha256(json.dumps(p58b, sort_keys=True).encode()).hexdigest()[:16]
    assert h == cfg["phase58b_config_hash"]


def test_clustering_no_future_in_source():
    src = (ROOT / "research" / "clustering.py").read_text()
    assert "net_R" not in src.split("def cluster")[1].split("def summarize")[0]
    assert "deepest_i" not in src


def test_truncation_invariance():
    n = 500
    rng = np.random.default_rng(0)
    trades = pd.DataFrame({
        "signal_i": np.arange(100, 100 + n),
        "entry_i": np.arange(100, 100 + n) + 1,
        "entry_price": 100 + rng.random(n),
        "direction": rng.choice(["LONG", "SHORT"], n),
        "net_R": rng.choice([-1, 2.5], n),
        "trade_id": [f"T{i}" for i in range(n)],
    })
    armed = rng.integers(50, 200, n)
    trades = trades.reset_index(drop=True)
    full = cluster_1m_opportunities(trades, armed)
    cut = 300
    sub_mask = trades["signal_i"].values < cut
    sub = trades.loc[sub_mask].copy()
    sub_armed = armed[sub_mask]
    partial = cluster_1m_opportunities(sub, sub_armed)
    full_sub = full.loc[full["signal_i"] < cut, ["trade_id", "opportunity_id"]]
    merged = partial[["trade_id", "opportunity_id"]].merge(full_sub, on="trade_id", suffixes=("_p", "_f"))
    assert (merged["opportunity_id_p"] == merged["opportunity_id_f"]).all()
