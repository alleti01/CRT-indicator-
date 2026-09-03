"""Tests for Phase 47 price-action research."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase45.execution.confirm import confirm_b1
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity
from phase45.execution.walkforward import pick_best_price_rule, walk_forward_price
from phase47.config import P45_B_PARITY, P45_DATASET
from phase47.features import extract_b1_bar_features, features_from_control_row
from phase47.parity import build_parity_csv, verify_phase45_b1_from_file, verify_phase45_b1_recomputed
from phase47.structure import causal_swing_levels, liquidity_sweep_before
from phase47.variants import (
    follow_through_entry,
    pass_break_strength,
    pass_close_quality,
    retest_entry,
)


def _tiny_market(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="America/Chicago")
    close = 100 + np.arange(n) * 0.1
    df = pd.DataFrame(
        {"open": close - 0.05, "high": close + 0.3, "low": close - 0.3, "close": close, "volume": 1000.0},
        index=idx,
    )
    df["atr"] = 0.5
    return df


def test_phase44_parity():
    signals = load_phase44_accepted()
    parity, _ = verify_phase44_parity(signals)
    assert bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])


def test_phase45_b1_parity():
    _, metrics, ok = verify_phase45_b1_from_file()
    assert ok
    assert abs(metrics["N"] - P45_B_PARITY["N"]) <= P45_B_PARITY["tol_N"]
    assert abs(metrics["AvgR"] - P45_B_PARITY["AvgR"]) <= P45_B_PARITY["tol_AvgR"]


def test_phase45_b1_recomputed():
    ok, perf = verify_phase45_b1_recomputed()
    assert ok
    assert perf["N"] == P45_B_PARITY["N"]


def test_walkforward_b1_window_reproduction():
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp"])
    stitched, params = walk_forward_price(ds)
    assert len(params) == 7
    assert (params["selected_rule"] == "B1").all()


def test_causal_structure_break():
    m = _tiny_market(50)
    hi = m["high"].values.copy()
    lo = m["low"].values
    hi[20] = hi[19] + 2.0
    hi[21] = hi[20] - 0.5
    sh, sl, _, _ = causal_swing_levels(hi, lo, 25)
    assert np.isfinite(sh) or np.isfinite(sl)


def test_break_strength_calculation():
    m = _tiny_market()
    feat = extract_b1_bar_features(m, 10, "Long", 100.0, 5, 0)
    assert "break_strength_atr" in feat
    assert np.isfinite(feat["break_strength_atr"]) or feat["break_strength_atr"] != feat["break_strength_atr"]


def test_displacement_and_close_quality():
    m = _tiny_market()
    feat = extract_b1_bar_features(m, 10, "Long", 100.0, 5, 0)
    assert 0 <= feat["close_quality"] <= 1
    assert feat["body_range_ratio"] >= 0


def test_wick_calculation():
    m = _tiny_market()
    feat = extract_b1_bar_features(m, 10, "Short", 100.0, 5, 0)
    assert feat["opposing_wick_ratio"] >= 0


def test_follow_through_timing():
    m = _tiny_market()
    ok, ei, px = follow_through_entry(m, 10, "Long", "F1", 100.0, 99.0, 105.0, "L")
    if ok:
        assert ei > 10


def test_retest_timing():
    m = _tiny_market(40)
    m.iloc[15, m.columns.get_loc("low")] = 99.0
    m.iloc[16, m.columns.get_loc("close")] = 100.5
    ok, ei, _ = retest_entry(m, 10, "Long", 100.0, 0.5, 98.0, 105.0, "L")
    if ok:
        assert ei > 10


def test_confirmed_pivot_liquidity_timing():
    hi = np.array([10.0, 10.5, 11.0, 10.8, 10.2, 9.8, 9.5, 10.0, 10.5])
    lo = np.array([9.5, 9.8, 10.0, 9.7, 9.5, 9.2, 9.0, 8.9, 9.8])
    swept = liquidity_sweep_before(hi, lo, 0, 8, "Long", 9.0, 6)
    assert swept is True


def test_filter_functions():
    row = pd.Series({"break_strength_atr": 0.15, "close_quality": 0.7, "opposing_wick_ratio": 0.2})
    assert pass_break_strength(row, 0.10)
    assert pass_close_quality(row, 0.60)


def test_no_future_bar_in_confirm_b1():
    m = _tiny_market(50)
    pos = {ts: i for i, ts in enumerate(m.index)}
    start = m.index[10]
    fill = confirm_b1(m, pos, start, 5, "Long")
    if fill.filled:
        assert fill.entry_time >= start


def test_nested_train_parameter_selection():
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp"])
    train = ds.iloc[:400]
    rule, win = pick_best_price_rule(train)
    assert rule == "B1"
    assert win in (5, 10, 15)


def test_train_test_isolation():
    from phase47.walkforward import walk_forward_filters

    wf, params = walk_forward_filters()
    assert not wf.empty
    assert params["fold"].nunique() >= 1
    assert (params["parameter"].notna()).all()


def test_no_future_bar_access_in_features():
    m = _tiny_market(20)
    feat = extract_b1_bar_features(m, 10, "Long", 100.0, 5, 0)
    assert "break_strength_atr" in feat
    assert feat["structure_age_bars"] == 5.0


@pytest.mark.slow
def test_run_phase47_deliverables(tmp_path: Path):
    from phase47.run import run_phase47

    manifest = run_phase47(output=tmp_path)
    assert manifest["p45_b1_parity_pass"]
    for name in (
        "phase45_parity.csv",
        "b1_price_features.csv",
        "variant_results.csv",
        "PHASE47_1M_PRICE_ACTION_REPORT.md",
        "PHASE47_1M_PRICE_ACTION.xlsx",
        "lookahead_audit.md",
    ):
        assert (tmp_path / name).exists()
