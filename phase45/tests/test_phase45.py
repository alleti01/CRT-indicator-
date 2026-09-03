"""Tests for Phase 45 forward validation framework."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase36.data import load_replay_market_15m
from phase45.config import (
    CHECKPOINTS,
    IMPULSE_THRESHOLD,
    Q_PASS_MIN,
    Q_RAW_LO,
    Q_TIER_A,
    Q_TIER_APLUS,
    Q_TIER_B,
)
from phase45.forward import build_forward_log, development_cutoff
from phase45.frozen import assert_frozen_constants_unchanged, evaluate_quality, quality_score
from phase45.parity import verify_development_parity, verify_pine_parity_windows
from phase45.run import run_phase45


def test_frozen_constants_match_phase44():
    assert assert_frozen_constants_unchanged()


def test_quality_score_formula():
    raw = 0.01066569852955479
    score = quality_score(raw)
    assert score > 60.0


def test_quality_thresholds():
    assert Q_PASS_MIN == pytest.approx(36.493, rel=1e-3)
    assert Q_TIER_B == pytest.approx(Q_PASS_MIN, rel=1e-3)
    assert Q_TIER_APLUS > Q_TIER_A > Q_TIER_B


def test_impulse_threshold_frozen():
    assert IMPULSE_THRESHOLD == 0.65


def test_pine_parity_windows():
    windows = verify_pine_parity_windows()
    assert windows["raw_match"].all()


def test_entry_eligibility():
    py = evaluate_quality(8847.25, 8824.75, 8803.5, 8819.5, "Long")
    assert py["quality_filter_pass"]
    assert py["confidence_tier"] == "A"


def test_forward_cutoff_enforcement():
    market = load_replay_market_15m()
    cutoff = development_cutoff(market)
    log, meta = build_forward_log(market, cutoff=cutoff)
    if not log.empty:
        assert (pd.to_datetime(log["timestamp"]) > cutoff).all()
    assert meta["forward_bars"] == 0


def test_no_future_leakage_in_log():
    market = load_replay_market_15m()
    cutoff = development_cutoff(market)
    log, _ = build_forward_log(market, cutoff=cutoff)
    assert log.empty  # no post-cutoff data yet


def test_checkpoint_definitions():
    assert 100 in CHECKPOINTS
    assert 500 in CHECKPOINTS


def test_deterministic_replay():
    market = load_replay_market_15m()
    cutoff = development_cutoff(market)
    log1, _ = build_forward_log(market, cutoff=cutoff)
    log2, _ = build_forward_log(market, cutoff=cutoff)
    if log1.empty:
        assert log2.empty
    else:
        pd.testing.assert_frame_equal(log1, log2)


def test_run_phase45_deliverables(tmp_path: Path):
    manifest = run_phase45(output=tmp_path)
    assert manifest["parity_pass"]
    assert manifest["frozen_parameters_unchanged"]
    required = [
        "forward_signal_log.csv",
        "accepted_signals.csv",
        "rejected_signals.csv",
        "forward_trade_log.csv",
        "confidence_results.csv",
        "validation_checkpoints.csv",
        "drift_monitor.csv",
        "FORWARD_VALIDATION_REPORT.md",
        "research_manifest.json",
    ]
    for name in required:
        assert (tmp_path / name).exists()


def test_development_parity_gate():
    result = verify_development_parity()
    assert result["parity_pass"]
    assert result["phase40_accepted_N"] == 3791
