"""Tests for Phase 49 forward validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity
from phase48.entries import load_frozen_entries
from phase48.parity import verify_entry_parity
from phase49.analysis import equity_curve, forward_metrics, sample_status
from phase49.bootstrap import build_bootstrap_reference, forward_percentile
from phase49.config import DATASET_TAG_FORWARD, DATASET_TAG_HISTORICAL, FORWARD_START_TIMESTAMP, HISTORICAL
from phase49.data_quality import audit_data_quality
from phase49.forward_engine import frozen_cutoff, frozen_forward_start, process_forward_b1_m0
from phase49.frozen import compute_model_hash, write_frozen_snapshot
from phase49.parity import build_historical_parity_csv, parity_passes, verify_m0_parity


def test_phase44_historical_parity():
    signals = load_phase44_accepted()
    p44, _ = verify_phase44_parity(signals)
    assert bool(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])


def test_phase45_b1_historical_parity():
    _, metrics, ok = verify_entry_parity()
    assert ok
    assert metrics["N"] == HISTORICAL["b1"]["N"]


def test_m0_historical_parity():
    _, ok = verify_m0_parity()
    assert ok


def test_frozen_model_hash():
    manifest, h = write_frozen_snapshot()
    assert len(h) == 64
    assert compute_model_hash() == h


def test_model_drift_detection():
    h1 = compute_model_hash()
    h2 = compute_model_hash()
    assert h1 == h2


def test_forward_start_exclusion():
    cutoff = frozen_cutoff()
    start = frozen_forward_start()
    assert start > cutoff


def test_dataset_separation_tags():
    assert DATASET_TAG_HISTORICAL != DATASET_TAG_FORWARD


def test_duplicate_signal_protection():
    from phase49.run import _append_immutable
    a = pd.DataFrame({"signal_id": ["A"], "x": [1]})
    b = pd.DataFrame({"signal_id": ["A"], "x": [2]})
    out = _append_immutable(a, b, "signal_id")
    assert len(out) == 1
    assert out.iloc[0]["x"] == 1


def test_causal_b1_empty_forward():
    sigs, trades = process_forward_b1_m0(pd.DataFrame())
    assert sigs.empty and trades.empty


def test_equity_curve():
    t = pd.DataFrame({"entry_time": pd.date_range("2024-01-01", periods=3, freq="D"), "net_r": [1.0, -0.5, 2.0]})
    eq = equity_curve(t)
    assert len(eq) == 3
    assert eq.iloc[-1]["cumulative_r"] == 2.5


def test_drawdown_calculation():
    t = pd.DataFrame({"entry_time": pd.date_range("2024-01-01", periods=3, freq="D"), "net_r": [2.0, -3.0, 1.0]})
    eq = equity_curve(t)
    assert eq["drawdown_r"].max() >= 0


def test_pf_calculation():
    t = pd.DataFrame({
        "net_r": [1.0, 1.0, -1.0],
        "wrong_direction": [0, 0, 0],
        "entry_time": pd.date_range("2024-01-01", periods=3, freq="D"),
        "mae_r": [0.1, 0.1, 0.1],
        "mfe_r": [0.2, 0.2, 0.2],
        "hold_minutes": [5, 5, 5],
    })
    m = forward_metrics(pd.DataFrame({"filled": [1, 1, 1]}), t)
    assert m["PF"] > 0


def test_fill_rate_calculation():
    sigs = pd.DataFrame({"filled": [1, 0, 1]})
    m = forward_metrics(sigs, pd.DataFrame())
    assert abs(m["fill_rate"] - 2 / 3) < 0.01


def test_wrong_direction_calculation():
    t = pd.DataFrame({"net_r": [1.0], "wrong_direction": [1], "entry_time": [pd.Timestamp("2024-01-01")], "mae_r": [0], "mfe_r": [0], "hold_minutes": [1]})
    m = forward_metrics(pd.DataFrame({"filled": [1]}), t)
    assert m["WrongDir"] == 1.0


def test_bootstrap_reproducibility():
    b1 = build_bootstrap_reference()
    b2 = build_bootstrap_reference()
    assert b1.equals(b2)


def test_forward_percentile_insufficient():
    hist = load_frozen_entries()["control_net_R"].astype(float).to_numpy()
    p = forward_percentile(np.array([]), hist)
    assert p["status"] == "INSUFFICIENT SAMPLE"


def test_sample_status_labels():
    assert sample_status(10) == "TOO EARLY"
    assert sample_status(50) == "PRELIMINARY"
    assert sample_status(200) == "STRONGER FORWARD EVIDENCE"


def test_data_quality_audit():
    dq = audit_data_quality()
    assert "pass" in dq
    assert "forward_15m_bars" in dq


def test_parity_gate():
    df = build_historical_parity_csv()
    assert parity_passes() == bool(df.loc[df["metric"] == "all_parity_pass", "value"].iloc[0])


def test_no_future_bar_access_forward_start():
    assert FORWARD_START_TIMESTAMP == "2026-06-29 00:00:00"


@pytest.mark.slow
def test_run_phase49_deliverables(tmp_path: Path):
    from phase49.run import run_phase49
    manifest = run_phase49(output=tmp_path, append=False)
    assert manifest["status"]["parity_status"] == "PASS"
    for name in (
        "forward_config.json",
        "historical_parity.csv",
        "forward_signals.csv",
        "forward_trades.csv",
        "PHASE49_FORWARD_VALIDATION_REPORT.md",
        "lookahead_contamination_audit.md",
    ):
        assert (tmp_path / name).exists()
