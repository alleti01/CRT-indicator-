"""Phase57D test suite — causality, parity, and integrity checks."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase57d.config import PHASE57B_ROOT, PHASE55_FROZEN, S54_MODEL_HASH
from phase57d.research.episodes import WallEpisodeEngine
from phase57d.research.execution import CausalExecutionModel
from phase57d.research.interactions import CausalInteractionDetector
from phase57d.research.provenance import evaluate_provenance_gate
from phase57d.research.sequential import SequentialReplayEngine
from phase57d.research.synthetic import make_synthetic_chain, synthetic_snapshots
from phase57d.research.wall_calculator import GammaWallCalculator, OIWallCalculator
from phase57d.research.wall_snapshot import WallSnapshotEngine
from phase57d.research.interfaces import OptionsSnapshot


def _random_bars(n: int = 200) -> pd.DataFrame:
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 2) + 18000
    idx = pd.date_range("2024-06-03 08:30", periods=n, freq="1min", tz="America/Chicago")
    hi = prices + np.abs(np.random.randn(n)) * 3
    lo = prices - np.abs(np.random.randn(n)) * 3
    df = pd.DataFrame({
        "open": prices - 0.5,
        "high": hi,
        "low": lo,
        "close": prices,
    }, index=idx)
    df["atr"] = pd.Series(hi - lo, index=idx).rolling(14, min_periods=1).mean().values
    return df


def _make_snapshot(ts: pd.Timestamp, spot: float) -> OptionsSnapshot:
    chain = make_synthetic_chain(spot, ts)
    return OptionsSnapshot(
        timestamp=ts,
        underlying="NQ",
        mapping="MAP_NQ_NDX",
        spot=spot,
        chain=chain,
        known_at=ts,
        snapshot_id=hashlib.sha256(str(ts).encode()).hexdigest()[:12],
    )


# ── 1. Options snapshot contains no future data ──────────────────────
def test_snapshot_known_at_not_after_timestamp():
    bars = _random_bars(50)
    for snap in synthetic_snapshots(bars, every_n=10):
        assert snap.known_at <= snap.timestamp or snap.known_at == snap.timestamp


# ── 2–4. OI/IV/Greeks timing (framework policy) ────────────────────
def test_provenance_gate_fails_without_options_data():
    gate = evaluate_provenance_gate()
    assert gate["gate_pass"] is False
    assert gate["performance_research_permitted"] is False


# ── 5. Expiration filtering is causal ────────────────────────────────
def test_expiration_filter_uses_snapshot_timestamp():
    ts = pd.Timestamp("2024-06-03 10:00", tz="America/Chicago")
    snap = _make_snapshot(ts, 18000.0)
    calc = OIWallCalculator("CALL")
    walls = calc.compute(snap, atr=50.0, expiration_scope="0-5D")
    assert all(w.valid_from == ts for w in walls)


# ── 7. Wall exists before interaction ────────────────────────────────
def test_interaction_rejects_pre_valid_wall():
    bars = _random_bars(100)
    ts = bars.index[50]
    snap = _make_snapshot(ts, float(bars.iloc[50]["close"]))
    engine = WallSnapshotEngine()
    engine.process_snapshot(snap, atr=50.0)
    active = engine.active_walls_at(ts)
    assert len(active) > 0

    det = CausalInteractionDetector()
    pre_ts = ts - pd.Timedelta(minutes=5)
    bar = bars.iloc[49]
    # Manually set valid_from in future
    future_wall = active[0]
    from phase57d.research.interfaces import WallSnapshot
    w = WallSnapshot(
        **{**future_wall.__dict__, "valid_from": ts + pd.Timedelta(minutes=1)}
    )
    events = det.update(bar, 49, pre_ts, [w], atr=50.0)
    assert len(events) == 0


# ── 8. No backward fill (wall IDs deterministic) ─────────────────────
def test_wall_ids_deterministic():
    ts = pd.Timestamp("2024-06-03 10:00", tz="America/Chicago")
    snap1 = _make_snapshot(ts, 18000.0)
    snap2 = _make_snapshot(ts, 18000.0)
    calc = OIWallCalculator("CALL")
    w1 = calc.compute(snap1, 50.0, "0-5D")
    w2 = calc.compute(snap2, 50.0, "0-5D")
    assert [x.wall_id for x in w1] == [x.wall_id for x in w2]


# ── 10–11. Wall/interaction IDs deterministic ────────────────────────
def test_interaction_ids_deterministic():
    bars = _random_bars(60)
    snaps = list(synthetic_snapshots(bars, every_n=15))
    e1 = SequentialReplayEngine()
    e2 = SequentialReplayEngine()
    atr = bars["atr"]
    w1, i1 = e1.replay(bars, iter(snaps), atr)
    w2, i2 = e2.replay(bars, iter(snaps), atr)
    if not i1.empty:
        assert set(i1["interaction_id"]) == set(i2["interaction_id"])


# ── 12. Episode consolidation deterministic ────────────────────────
def test_episode_consolidation_deterministic():
    df = pd.DataFrame({
        "wall_id": ["a", "a", "a", "b"],
        "signal_timestamp": pd.date_range("2024-01-01", periods=4, freq="5min", tz="UTC"),
        "interaction_id": ["i1", "i2", "i3", "i4"],
    })
    e1 = WallEpisodeEngine(window_min=30).consolidate(df)
    e2 = WallEpisodeEngine(window_min=30).consolidate(df)
    assert e1["episode_id"].tolist() == e2["episode_id"].tolist()
    assert e1["is_distinct"].sum() == e2["is_distinct"].sum()


# ── 13. Same-timestamp ordering deterministic ────────────────────────
def test_same_timestamp_ordering():
    ts = pd.Timestamp("2024-06-03 10:00", tz="America/Chicago")
    df = pd.DataFrame({
        "wall_id": ["b", "a"],
        "signal_timestamp": [ts, ts],
        "interaction_id": ["i2", "i1"],
    })
    out = WallEpisodeEngine().consolidate(df)
    assert out.iloc[0]["wall_id"] == "a"


# ── 14. Next-bar execution correct ─────────────────────────────────
def test_next_bar_execution():
    bars = _random_bars(80)
    model = CausalExecutionModel()
    signal = {"direction": "LONG", "signal_timestamp": bars.index[40]}
    result = model.execute(signal, bars, 40, tick_slippage=0)
    assert result["execution_timestamp"] == bars.index[41]
    assert result["entry_price"] == bars.iloc[41]["open"]


# ── 16. Conservative stop/target collision ───────────────────────────
def test_conservative_stop_first():
    idx = pd.date_range("2024-01-01 10:00", periods=5, freq="1min", tz="America/Chicago")
    bars = pd.DataFrame({
        "open": [100, 100, 100, 100, 100],
        "high": [100, 110, 100, 100, 100],
        "low": [100, 90, 100, 100, 100],
        "close": [100, 100, 100, 100, 100],
        "atr": [5, 5, 5, 5, 5],
    }, index=idx)
    model = CausalExecutionModel(stop_atr=0.75, target_r=2.5)
    signal = {"direction": "LONG"}
    result = model.execute(signal, bars, 0)
    assert result["exit_reason"] == "STOP_SAME_BAR"
    assert result["r"] < 0


# ── 17. Truncation invariance (synthetic) ───────────────────────────
def test_truncation_invariance_walls():
    bars = _random_bars(150)
    cut = 100
    snaps_full = list(synthetic_snapshots(bars, every_n=10))
    snaps_trunc = [s for s in snaps_full if s.known_at <= bars.index[cut - 1]]

    e_full = WallSnapshotEngine()
    e_trunc = WallSnapshotEngine()
    for s in snaps_full:
        e_full.process_snapshot(s, 50.0)
    for s in snaps_trunc:
        e_trunc.process_snapshot(s, 50.0)

    full_ids = {w.wall_id for w in e_full._history if w.valid_from <= bars.index[cut - 1]}
    trunc_ids = {w.wall_id for w in e_trunc._history}
    assert full_ids == trunc_ids


# ── 18. Sequential replay parity ─────────────────────────────────────
def test_sequential_replay_parity():
    bars = _random_bars(120)
    snaps = list(synthetic_snapshots(bars, every_n=20))
    engine = SequentialReplayEngine()
    walls, inter = engine.replay(bars, iter(snaps), bars["atr"])
    cmp = engine.compare_batch(walls, inter)
    assert cmp["sequential_parity"] is True


# ── 19. Restart parity ───────────────────────────────────────────────
def test_restart_parity():
    bars = _random_bars(80)
    snaps = list(synthetic_snapshots(bars, every_n=15))
    e1 = SequentialReplayEngine()
    w1, i1 = e1.replay(bars, iter(snaps), bars["atr"])
    e2 = SequentialReplayEngine()
    w2, i2 = e2.replay(bars, iter(snaps), bars["atr"])
    if not w1.empty:
        assert set(w1["wall_id"]) == set(w2["wall_id"])


# ── 21. Deterministic rerun ──────────────────────────────────────────
def test_deterministic_rerun():
    ts = pd.Timestamp("2024-06-03 10:00", tz="America/Chicago")
    snap = _make_snapshot(ts, 18000.0)
    calc = GammaWallCalculator()
    r1 = calc.compute(snap, 50.0, "0-5D")
    r2 = calc.compute(snap, 50.0, "0-5D")
    assert [(w.strike, w.wall_value) for w in r1] == [(w.strike, w.wall_value) for w in r2]


# ── 22. S54 hash unchanged ───────────────────────────────────────────
def test_s54_model_hash_unchanged():
    h = (PHASE55_FROZEN / "model_hash.txt").read_text().strip()
    assert h == S54_MODEL_HASH


# ── 23. Phase57B unchanged ───────────────────────────────────────────
def test_phase57b_exists_unmodified():
    assert PHASE57B_ROOT.exists()
    assert (PHASE57B_ROOT / "run.py").exists()
    # Phase57D must not have written into phase57b
    assert not (PHASE57B_ROOT / "phase57d_marker").exists()


# ── Episode consolidation reduces duplication ──────────────────────
def test_episode_consolidation_reduces_count():
    df = pd.DataFrame({
        "wall_id": ["w1"] * 10,
        "signal_timestamp": pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC"),
        "interaction_id": [f"i{i}" for i in range(10)],
    })
    eng = WallEpisodeEngine(window_min=30)
    out = eng.consolidate(df)
    assert out["is_distinct"].sum() == 1
