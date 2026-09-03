"""Phase58H causality and parity tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def test_frozen_integrity():
    cfg = json.load(open(ROOT / "phase58h" / "config" / "phase58h_frozen.json"))
    assert _hash_file(ROOT / "phase58f" / "config" / "phase58f_frozen.json") == cfg["phase58f_config_hash"]
    assert _hash_file(ROOT / "phase58g" / "config" / "phase58g_frozen.json") == cfg["phase58g_config_hash"]


def test_p4_baseline_parity():
    from phase58f.research.policies import apply_policy
    from phase58b.research.simulation import metrics

    df = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    if "net_R" not in df.columns:
        df = df.merge(tr[["trade_id", "net_R"]], on="trade_id")
    else:
        df = df.drop(columns=[c for c in df.columns if c.startswith("net_R_") and c != "net_R"], errors="ignore")
    p4 = apply_policy(df, "P4")
    kept = df.loc[p4 == "KEEP"]
    assert (p4 == "ABSTAIN").sum() == 79
    assert len(kept) == 61874
    m = metrics(kept["net_R"].values)
    assert abs(m["TotalR"] - 10998.92) < 5


def test_high_conflicted_parity():
    from phase58g.research.forensics import enrich

    g = pd.read_parquet(ROOT / "phase58g" / "results" / "high_forensics.parquet")
    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    audit = audit.merge(tr[["trade_id", "net_R"]], on="trade_id")
    h = enrich(audit)
    merged = h[["trade_id", "high_subtype"]].merge(g[["trade_id", "high_subtype"]], on="trade_id", suffixes=("_h", "_g"))
    assert (merged["high_subtype_h"] == merged["high_subtype_g"]).all()


def test_h_models_zero_delay():
    from phase58g.research.forensics import enrich
    from phase58h.research.filters import apply_h_model

    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    tr = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    full = enrich(audit.merge(tr[["trade_id", "net_R"]], on="trade_id"))
    for model in ["H0", "H1", "H2", "H3", "H4"]:
        dec = apply_h_model(full, model)
        assert set(dec.unique()) <= {"KEEP", "ABSTAIN"}
    h1_new = (apply_h_model(full, "H1") == "ABSTAIN").sum() - (apply_h_model(full, "H0") == "ABSTAIN").sum()
    assert 1700 < h1_new < 1800
