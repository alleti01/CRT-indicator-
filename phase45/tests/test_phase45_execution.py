"""Tests for Phase 45 1m execution study."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from phase45.execution.config import P44_PARITY, RESULTS
from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase45.execution.run import build_dataset, run_execution_study
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity


def test_phase44_parity_gate():
    signals = load_phase44_accepted()
    parity, _ = verify_phase44_parity(signals)
    assert bool(parity.loc[parity["metric"] == "parity_pass", "value"].iloc[0])
    assert int(parity.loc[parity["metric"] == "N", "value"].iloc[0]) == P44_PARITY["N"]


def test_causal_1m_confirmation_no_lookahead():
    market = load_market_1m()
    pos = {ts: i for i, ts in enumerate(market.index)}
    signals = load_phase44_accepted().head(20)
    for sig in signals.itertuples(index=False):
        act = pd.Timestamp(sig.actionable_timestamp).tz_convert(market.index.tz)
        fill = confirm_b1(market, pos, act, 10, sig.direction)
        if fill.filled:
            assert fill.entry_time >= act
            assert fill.delay_min >= 0


def test_build_dataset_lookahead_columns():
    market = load_market_1m()
    signals = load_phase44_accepted().head(10)
    from phase45.execution.signals import attach_behavior_15m

    behavior = attach_behavior_15m(signals)
    df = build_dataset(market, signals, behavior)
    assert (df["actionable_timestamp"] == df["first_eligible_1m"]).all()
    for rule in ("B1",):
        for win in (5, 10):
            col = f"{rule}_w{win}_lookahead_ok"
            if col in df.columns:
                assert df.loc[df[f"{rule}_w{win}_filled"], col].all()


@pytest.mark.slow
def test_run_execution_study_deliverables(tmp_path: Path):
    manifest = run_execution_study(output=tmp_path)
    assert manifest["parity_pass"]
    required = [
        "phase44_parity.csv",
        "phase44_signal_timestamps.csv",
        "one_minute_execution_dataset.csv",
        "price_confirmation_comparison.csv",
        "volume_confirmation_comparison.csv",
        "matched_signal_comparison.csv",
        "unfilled_signal_analysis.csv",
        "quality_tier_results.csv",
        "signal_type_results.csv",
        "yearly_results.csv",
        "cost_stress.csv",
        "wrong_direction_analysis.csv",
        "entry_delay_analysis.csv",
        "mfe_mae_comparison.csv",
        "walk_forward_results.csv",
        "parameter_stability.csv",
        "lookahead_audit.md",
        "PHASE45_15M_1M_EXECUTION_REPORT.md",
        "PHASE45_15M_1M_EXECUTION.xlsx",
        "research_manifest.json",
    ]
    for name in required:
        assert (tmp_path / name).exists(), name


def test_results_folder_exists_after_full_run():
    if not (RESULTS / "research_manifest.json").exists():
        pytest.skip("full execution study not run yet")
    assert (RESULTS / "phase44_parity.csv").exists()
