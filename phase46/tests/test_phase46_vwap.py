"""Tests for Phase 46 VWAP research."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase45.execution.signals import verify_phase44_parity, load_phase44_accepted
from phase46.baseline import apply_b0, build_oos_frame, verify_p45_parity
from phase46.config import B0_WINDOW_MIN, V3_SLOPE_WINDOWS, V4_MAX_DIST_ATR
from phase46.vwap import attach_session_vwap, detect_reclaim_window, hlc3, signed_vwap_distance, vwap_retest_entry


def _tiny_market() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=20, freq="1min", tz="America/Chicago")
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(rng.normal(0, 0.1, len(idx)))
    df = pd.DataFrame(
        {
            "open": close - 0.05,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": rng.integers(100, 500, len(idx)).astype(float),
        },
        index=idx,
    )
    df["atr"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
    return attach_session_vwap(df)


def test_vwap_session_reset():
    m = _tiny_market()
    assert m["vwap"].notna().all()
    assert m["session_date"].nunique() >= 1


def test_causal_vwap_no_future_leak():
    m = _tiny_market()
    i = 10
    sub = m.iloc[: i + 1]
    manual = (sub["hlc3"] * sub["volume"]).sum() / sub["volume"].sum()
    assert abs(m.iloc[i]["vwap"] - manual) < 1e-9


def test_reclaim_detection():
    m = _tiny_market()
    ok = detect_reclaim_window(m, 0, 5, "Long")
    assert isinstance(ok, bool)


def test_vwap_slope_columns():
    m = _tiny_market()
    for n in V3_SLOPE_WINDOWS:
        assert f"vwap_slope_{n}" in m.columns


def test_distance_calculation():
    d = signed_vwap_distance(101.0, 100.0, "Long")
    assert d > 0
    d2 = signed_vwap_distance(99.0, 100.0, "Long")
    assert d2 < 0


def test_vwap_retest_forward_only():
    m = _tiny_market()
    ok, j, px = vwap_retest_entry(m, 3, "Long", tol_atr=0.5, max_wait=3)
    if ok:
        assert j > 3
        assert np.isfinite(px)


def test_phase44_parity():
    signals = load_phase44_accepted()
    parity, _ = verify_phase44_parity(signals)
    assert bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])


def test_b0_baseline_reproducible():
    oos = apply_b0(build_oos_frame())
    parity = verify_p45_parity(oos)
    assert bool(parity.loc[parity["metric"] == "p44_parity_pass", "value"].iloc[0])
    assert B0_WINDOW_MIN == 10


def test_train_test_isolation_in_walkforward():
    from phase46.walkforward import _slice
    from phase46.config import WALK_FORWARD_FOLDS

    oos = build_oos_frame()
    # OOS frame only contains TEST segments (2020+); use fold 2 as example
    _tr_s, _tr_e, te_s, te_e = WALK_FORWARD_FOLDS[1]
    test = _slice(oos, te_s, te_e)
    assert not test.empty
    tz = test["marker_bar_timestamp"].dt.tz
    assert test["marker_bar_timestamp"].min() >= pd.Timestamp(te_s, tz=tz)
    assert test["marker_bar_timestamp"].max() <= pd.Timestamp(te_e, tz=tz)


@pytest.mark.slow
def test_run_phase46_deliverables(tmp_path: Path):
    from phase46.run import run_phase46

    manifest = run_phase46(output=tmp_path)
    assert manifest["p44_parity_pass"]
    for name in (
        "phase45_parity.csv",
        "vwap_trade_features.csv",
        "variant_results.csv",
        "walk_forward_results.csv",
        "lookahead_audit.md",
        "PHASE46_VWAP_REPORT.md",
        "research_manifest.json",
    ):
        assert (tmp_path / name).exists()
