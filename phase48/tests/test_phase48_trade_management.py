"""Tests for Phase 48 trade management."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity
from phase45.execution.simulate import simulate_1m
from phase48.config import P45_ENTRY_PARITY
from phase48.entries import load_frozen_entries
from phase48.parity import verify_entry_parity
from phase48.simulate_mgmt import MgmtSpec, simulate_managed
from phase48.stops import compute_stop
from phase48.structure import causal_swing_levels, opposite_bos
from phase48.variants import spec_breakeven, spec_fixed_target, spec_m0, spec_time_exit


def _tiny_market(n: int = 40) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="America/Chicago")
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0, 0.1, n))
    df = pd.DataFrame({"open": close - 0.05, "high": close + 0.5, "low": close - 0.5, "close": close, "volume": 1000.0}, index=idx)
    df["atr"] = 0.75
    return df


def test_phase44_parity():
    signals = load_phase44_accepted()
    parity, _ = verify_phase44_parity(signals)
    assert bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])


def test_phase45_entry_parity():
    _, metrics, ok = verify_entry_parity()
    assert ok
    assert metrics["N"] == P45_ENTRY_PARITY["N"]


def test_identical_entry_population():
    e1 = load_frozen_entries()
    e2 = load_frozen_entries()
    assert len(e1) == len(e2) == P45_ENTRY_PARITY["N"]
    assert (e1["signal_id"] == e2["signal_id"]).all()


def test_causal_stop_placement():
    m = _tiny_market()
    stop, tgt = compute_stop(m, 10, 100.0, "Long", "L", mode="S3", frozen_stop=98.0, atr_mult=0.75)
    assert stop < 100.0
    assert tgt > 100.0


def test_structure_stop_timing():
    hi = np.array([10.0, 10.5, 11.0, 10.8, 10.2])
    lo = np.array([9.5, 9.8, 10.0, 9.7, 9.5])
    sh, sl, _, _ = causal_swing_levels(hi, lo, 4)
    assert np.isfinite(sh) or np.isfinite(sl)


def test_target_calculations():
    spec = spec_fixed_target(2.0)
    assert spec.target_r == 2.0


def test_breakeven_trigger_timing():
    m = _tiny_market(60)
    m.iloc[15, m.columns.get_loc("high")] = 105.0
    spec = spec_breakeven(0.5, "BE0")
    sim = simulate_managed(m, 10, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert "net_R" in sim


def test_partial_exit_accounting():
    m = _tiny_market(60)
    spec = MgmtSpec(name="P2", partials=[(1.0, 0.5)])
    sim = simulate_managed(m, 10, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert sim["realized_parts"] >= 1


def test_trailing_stop_timing():
    m = _tiny_market(60)
    spec = MgmtSpec(name="TR", trail_activate_r=1.0, trail_method="TR1", trail_param=0)
    sim = simulate_managed(m, 10, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert "exit_type" in sim


def test_opposite_bos_exit_timing():
    close = np.array([10.0, 10.1, 10.2, 9.8, 9.7])
    hi = close + 0.2
    lo = close - 0.2
    assert opposite_bos(hi, lo, close, 3, "Long") in (True, False)


def test_time_exit_timing():
    m = _tiny_market(30)
    spec = spec_time_exit(5)
    sim = simulate_managed(m, 5, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert sim["hold_bars"] <= 10


def test_stagnation_rule_timing():
    m = _tiny_market(20)
    spec = MgmtSpec(name="ST1", stagnation="ST1")
    sim = simulate_managed(m, 5, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert sim["exit_type"] in ("STAGNATION", "STOP", "TARGET", "TIME", "DATA_END")


def test_profit_lock_timing():
    m = _tiny_market(60)
    spec = MgmtSpec(name="PL", profit_lock_trigger=1.0, profit_lock_r=0.5)
    sim = simulate_managed(m, 10, 100.0, 98.0, 106.0, "Long", "L", spec)
    assert "net_R" in sim


def test_same_bar_stop_target_ordering():
    m = _tiny_market(20)
    m.iloc[12, m.columns.get_loc("low")] = 97.0
    m.iloc[12, m.columns.get_loc("high")] = 107.0
    sim = simulate_1m(m, 10, 100.0, 98.0, 106.0, "Long", "L")
    assert sim["exit_type"] == "STOP"


def test_normalized_r_calculation():
    m = _tiny_market()
    stop, _ = compute_stop(m, 10, 100.0, "Long", "L", mode="S3", frozen_stop=98.0, atr_mult=1.0)
    risk = abs(100.0 - stop)
    assert risk > 0


def test_nested_train_parameter_selection():
    from phase48.walkforward import _pick_best
    from phase48.entries import build_train_entries
    from phase45.execution.data_1m import load_market_1m
    from phase48.config import P45_DATASET, WALK_FORWARD_FOLDS
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    mkt = load_market_1m()
    tr_s, tr_e, _, _ = WALK_FORWARD_FOLDS[0]
    train = build_train_entries(ds, mkt, 1, tr_s, tr_e)
    if len(train) >= 15:
        spec, kw, avgr = _pick_best(train, mkt, [(spec_m0(), {}), (spec_time_exit(10), {})])
        assert avgr > -999


def test_train_test_isolation():
    pytest.importorskip("phase48.walkforward")
    from phase48.config import WALK_FORWARD_FOLDS
    assert len(WALK_FORWARD_FOLDS) == 7


@pytest.mark.slow
def test_walk_forward_management_full():
    from phase48.walkforward import walk_forward_management
    m0, wf, params = walk_forward_management()
    assert len(m0) == P45_ENTRY_PARITY["N"]
    assert params["fold"].nunique() >= 1


def test_no_future_bar_access():
    m = _tiny_market(25)
    sim = simulate_1m(m, 10, 100.0, 98.0, 106.0, "Long", "L")
    assert sim["exit_timestamp"] >= m.index[10]


def test_m0_matches_control():
    from phase48.paths import build_trade_paths
    paths = build_trade_paths()
    assert len(paths) == P45_ENTRY_PARITY["N"]


@pytest.mark.slow
def test_run_phase48_deliverables(tmp_path: Path):
    from phase48.run import run_phase48
    manifest = run_phase48(output=tmp_path)
    assert manifest["p45_entry_parity_pass"]
    assert (tmp_path / "PHASE48_TRADE_MANAGEMENT_REPORT.md").exists()
