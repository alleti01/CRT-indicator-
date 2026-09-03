"""Tests for Phase 44B validation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase44b.config import EXP_TOTAL, WALK_FORWARD_FOLDS
from phase44b.features import build_dataset, feature_audit_text, normalize_score, ret_n_atr_phase43, ret_n_atr_pine
from phase44b.run import run_phase44b


def test_ret_formulas_match():
    assert ret_n_atr_phase43(100.0, 99.0, 1) == ret_n_atr_pine(100.0, 99.0, 1)
    assert ret_n_atr_phase43(100.0, 101.0, -1) == ret_n_atr_pine(100.0, 101.0, -1)


def test_normalize_score_bounds():
    s = normalize_score(np.array([-1.0, 0.0, 1.0]), -0.5, 0.5)
    assert s.min() >= 0
    assert s.max() <= 100


def test_feature_audit_documents_parity():
    txt = feature_audit_text()
    assert "EXACT FEATURE PARITY: YES" in txt
    assert "pct_change" in txt


def test_dataset_feature_parity():
    df = build_dataset()
    assert len(df) == EXP_TOTAL
    assert df["feature_parity_ok"].all()


def test_walk_forward_folds_count():
    assert len(WALK_FORWARD_FOLDS) == 7


def test_run_phase44b_produces_deliverables(tmp_path: Path):
    manifest = run_phase44b(output=tmp_path)
    assert manifest["parity_pass"]
    assert manifest["feature_parity"]
    required = [
        "phase40_parity.csv",
        "feature_definition_audit.md",
        "walk_forward_fold_parameters.csv",
        "walk_forward_predictions.csv",
        "walk_forward_accepted.csv",
        "walk_forward_rejected.csv",
        "FINAL_QUALITY_VALIDATION_REPORT.md",
        "research_manifest.json",
    ]
    for name in required:
        assert (tmp_path / name).exists()


def test_no_lookahead_calibration(tmp_path: Path):
    run_phase44b(output=tmp_path)
    folds = pd.read_csv(tmp_path / "walk_forward_fold_parameters.csv")
    preds = pd.read_csv(tmp_path / "walk_forward_predictions.csv", parse_dates=["marker_bar_timestamp"])
    for _, row in folds.iterrows():
        te_s = pd.Timestamp(row["test_start"], tz="UTC")
        te_e = pd.Timestamp(row["test_end"], tz="UTC")
        sub = preds.loc[(preds["marker_bar_timestamp"] >= te_s) & (preds["marker_bar_timestamp"] <= te_e)]
        assert (sub["train_q05"] == row["train_q05"]).all()
        assert (sub["train_threshold"] == row["train_threshold"]).all()
