"""Phase58D causality and memory tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]

from phase58c.research.clustering import cluster_1m_opportunities
from phase58d.research.engine import online_memory_at_signals
from phase58d.research.opportunity_memory import OpportunityMemory


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_hashes_unchanged():
    cfg = json.load(open(ROOT / "phase58d" / "config" / "phase58d_frozen.json"))
    assert _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json") == cfg["phase58_v1_hash"]
    assert (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip() == cfg["s54_model_hash"]


def test_online_memory_matches_offline_clustering():
    trades = pd.read_parquet(ROOT / "phase58" / "results" / "trades.parquet").head(5000)
    dec = pd.read_parquet(
        ROOT / "phase58" / "results" / "decisions.parquet",
        filters=[("decision", "in", ["TAKE_LONG", "TAKE_SHORT"])],
    )
    armed = trades.merge(dec[["bar_i", "armed_i"]], left_on="signal_i", right_on="bar_i", how="left")["armed_i"].fillna(-1).values.astype(int)
    offline = cluster_1m_opportunities(trades, armed, structural_gap=30)
    online = online_memory_at_signals(trades, structural_gap=30)
    o = offline.sort_values("signal_i").reset_index(drop=True)["opportunity_id"].values
    n = online.sort_values("signal_i").reset_index(drop=True)["opportunity_id"].values
    assert (o == n).all()


def test_truncation_invariance_memory():
    trades = pd.read_parquet(ROOT / "phase58" / "results" / "trades.parquet").head(2000)
    cut = 1000
    sub = trades.iloc[:cut]
    full = online_memory_at_signals(trades.head(2000), 30)
    part = online_memory_at_signals(sub, 30)
    assert part.iloc[-1]["opportunity_id"] == full.iloc[cut - 1]["opportunity_id"]


def test_opportunity_memory_deterministic():
    mem1 = OpportunityMemory(30)
    mem2 = OpportunityMemory(30)
    signals = [(100, 100.0, "LONG"), (105, 101.0, "LONG"), (200, 99.0, "LONG")]
    ids1, ids2 = [], []
    for i, p, d in signals:
        o1, _ = mem1.match_or_create(i, p, d)
        o2, _ = mem2.match_or_create(i, p, d)
        ids1.append(o1.opportunity_id)
        ids2.append(o2.opportunity_id)
    assert ids1 == ids2
    assert ids1[0] == ids1[1]  # same opportunity
    assert ids1[0] != ids1[2]  # gap reset
