"""Phase58G causality and forensic tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_hashes():
    cfg = json.load(open(ROOT / "phase58g" / "config" / "phase58g_frozen.json"))
    assert _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json") == cfg["phase58_v1_hash"]
    assert _hash_file(ROOT / "phase58f" / "config" / "phase58f_frozen.json") == cfg["phase58f_config_hash"]


def test_high_subtype_split():
    from phase58g.research.forensics import enrich

    df = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    if "net_R" not in df.columns:
        df = df.merge(tr[["trade_id", "net_R"]], on="trade_id")
    full = enrich(df)
    high = full.loc[full["direction_confidence_band"] == "HIGH"]
    assert set(high["high_subtype"].unique()) <= {"HIGH_CLEAN", "HIGH_CONFLICTED", "HIGH_REVERSAL", ""}
    conflicted = high.loc[high["high_subtype"] == "HIGH_CONFLICTED"]
    assert len(conflicted) > 10000
    assert conflicted["net_R"].mean() < 0


def test_high_conflicted_negative_expectancy():
    from phase58g.research.forensics import enrich, high_subtype_table

    df = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    if "net_R" not in df.columns:
        df = df.merge(tr[["trade_id", "net_R"]], on="trade_id")
    tbl = high_subtype_table(enrich(df))
    conf = tbl.loc[tbl["high_subtype"] == "HIGH_CONFLICTED"].iloc[0]
    rev = tbl.loc[tbl["high_subtype"] == "HIGH_REVERSAL"].iloc[0]
    assert conf["AvgR"] < 0
    assert rev["AvgR"] > 0


def test_p4_unchanged():
    from phase58f.research.policies import apply_policy

    df = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    df = df.merge(tr[["trade_id", "net_R"]], on="trade_id", how="left")
    p4 = apply_policy(df, "P4")
    assert (p4 == "ABSTAIN").sum() == 79
