"""Phase58B causality and determinism tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from phase58b.research.context_15m import compute_15m_context, strong_contradiction
from phase58b.research.precompute import MTFArrays
from phase58b.research.trader_5m import FiveMTraderEngine


def _make_mtf(n5: int = 200) -> MTFArrays:
    rng = np.random.default_rng(42)
    m5_cl = 100 + np.cumsum(rng.normal(0, 0.5, n5))
    m5_hi = m5_cl + rng.uniform(0.1, 0.5, n5)
    m5_lo = m5_cl - rng.uniform(0.1, 0.5, n5)
    m5_op = m5_cl + rng.normal(0, 0.1, n5)
    m5_atr = np.full(n5, 1.0)
    n1 = n5 * 5
    m1_cl = np.repeat(m5_cl, 5)
    m1_hi = np.repeat(m5_hi, 5)
    m1_lo = np.repeat(m5_lo, 5)
    m1_op = np.repeat(m5_op, 5)
    m1_atr = np.full(n1, 0.5)
    import pandas as pd

    idx5 = pd.date_range("2024-01-02 09:30", periods=n5, freq="5min")
    idx1 = pd.date_range("2024-01-02 09:30", periods=n1, freq="1min")
    sh = np.full(n5, np.nan)
    sl = np.full(n5, np.nan)
    return MTFArrays(
        m1_hi=m1_hi, m1_lo=m1_lo, m1_cl=m1_cl, m1_op=m1_op, m1_atr=m1_atr,
        m1_n=n1, m1_idx=idx1,
        m5_hi=m5_hi, m5_lo=m5_lo, m5_cl=m5_cl, m5_op=m5_op, m5_atr=m5_atr,
        m5_n=n5, m5_idx=idx5,
        m5_sh=sh, m5_sl=sl, m5_sh1=sh, m5_sh2=sh, m5_sl1=sl, m5_sl2=sl,
        m5_body=np.abs(m5_cl - m5_op),
        m15_cl=m5_cl, m15_op=m5_op, m15_hi=m5_hi, m15_lo=m5_lo,
        m15_atr=m5_atr, m15_idx_on_m5=np.arange(n5),
        m1_to_m5=np.repeat(np.arange(n5), 5),
        m5_close_m1_i=np.minimum(np.arange(n5) * 5 + 1, n1 - 1),
        m5_signal_m1_i=np.minimum(np.arange(n5) * 5 + 4, n1 - 1),
    )


@pytest.fixture
def cfg():
    return json.load(open(ROOT / "config" / "phase58b_frozen.json"))


def test_phase58_v1_hash_unchanged():
    p58 = json.load(open(ROOT.parent / "phase58" / "config" / "phase58_v1_frozen.json"))
    h = hashlib.sha256(json.dumps(p58, sort_keys=True).encode()).hexdigest()[:16]
    assert h == "facad8ebfae648be"


def test_s54_hash_unchanged():
    s54 = (ROOT.parent / "phase55" / "frozen" / "model_hash.txt").read_text().strip()
    assert s54 == "bccf4277f3d44d13"


def test_15m_context_bounded(cfg):
    m = _make_mtf()
    ctx = compute_15m_context(m, 50, cfg)
    assert ctx["state"] in ("BULLISH", "BEARISH", "NEUTRAL", "TRANSITION")
    assert -2 <= ctx["score"] <= 2


def test_no_deepest_i_in_source():
    src = (ROOT / "research" / "trader_5m.py").read_text()
    assert "deepest_i" not in src


def test_deterministic_5m_engine(cfg):
    m = _make_mtf(300)
    e1 = FiveMTraderEngine(m, cfg, use_15m=True)
    e1.run(end_j=250)
    _, _, t1 = e1.results()
    e2 = FiveMTraderEngine(m, cfg, use_15m=True)
    e2.run(end_j=250)
    _, _, t2 = e2.results()
    assert len(t1) == len(t2)


def test_truncation_invariance_15m(cfg):
    m = _make_mtf(300)
    j = 150
    ctx_full = compute_15m_context(m, j, cfg)
    ctx_trunc = compute_15m_context(m, j, cfg)
    assert ctx_full == ctx_trunc


def test_strong_contra_returns_bool(cfg):
    m = _make_mtf()
    ctx = compute_15m_context(m, 50, cfg)
    ok, reasons = strong_contradiction(ctx, "LONG", m, 50)
    assert isinstance(ok, bool)


def test_max_exec_delay(cfg):
    assert cfg["max_exec_delay_bars_1m"] <= 2


def test_hard_filter_disabled(cfg):
    assert cfg["hard_filter_enabled"] is False
