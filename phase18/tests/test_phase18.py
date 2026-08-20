from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
PHASE18 = ROOT / "phase18"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_baseline_and_frozen_candidate_hashes_are_exact() -> None:
    reference = pd.read_csv(ROOT / "phase16/results/oos/model_comparison.csv")
    baseline = pd.read_csv(PHASE18 / "baseline_gate/model_comparison.csv")
    assert reference.equals(baseline)
    assert digest(ROOT / "phase16/results/oos/trades.csv") == digest(
        PHASE18 / "baseline_gate/trades.csv"
    )
    manifest = json.loads((PHASE18 / "results/reproducibility_manifest.json").read_text())
    assert digest(ROOT / "phase17/results/frozen_candidates.json") == manifest[
        "phase17_frozen_candidates_sha256"
    ]


def test_data_validation_gate_and_zero_overlap() -> None:
    validation = json.loads((PHASE18 / "data_validation/data_validation.json").read_text())
    assert validation["coverage_left"] is True
    assert validation["coverage_right"] is True
    assert validation["duplicate_download_rows"] == 0
    assert validation["duplicate_5m_rows"] == 0
    assert validation["invalid_ohlc_rows"] == 0
    assert validation["development_overlap_rows"] == 0
    assert validation["oos_5m_rows"] == 212019
    assert validation["maximum_absolute_adjusted_roll_gap_points"] == 0.0


def test_candidate_trade_exports_match_exact_frozen_conditions() -> None:
    c1 = pd.read_csv(PHASE18 / "trades_C1.csv")
    c2 = pd.read_csv(PHASE18 / "trades_C2.csv")
    assert len(c1) == 414
    assert len(c2) == 469
    assert set(c1["direction_name"]) == {"Short"}
    assert set(c1["session_name"]) == {"Premarket"}
    assert set(c2["direction_name"]) == {"Short"}
    assert set(c2["score_band"]) == {"90-94"}
    assert set(c1["model"]) == {"C1"}
    assert set(c2["model"]) == {"C2"}


def test_predeclared_primary_gate_fails_both_candidates() -> None:
    result = pd.read_csv(PHASE18 / "pass_fail.csv").set_index("candidate_id")
    assert not bool(result.loc["C1", "primary_pass"])
    assert not bool(result.loc["C2", "primary_pass"])
    assert result.loc["C1", "classification"] == "D — OOS FAIL"
    assert result.loc["C2", "classification"] == "D — OOS FAIL"
    assert not bool(result.loc["C2", "profit_factor_over_1_05"])
    assert not bool(result.loc["C2", "standard_conservative_total_R_positive"])


def test_cost_stress_degrades_monotonically() -> None:
    costs = pd.read_csv(PHASE18 / "cost_stress.csv")
    order = ["Ideal/current", "Modest", "Standard conservative", "Severe", "Extreme"]
    for candidate_id in ("C1", "C2"):
        totals = costs.loc[costs["candidate_id"] == candidate_id].set_index("scenario").loc[
            order, "total_R"
        ]
        assert totals.is_monotonic_decreasing


def test_calendar_outputs_are_complete() -> None:
    monthly = pd.read_csv(PHASE18 / "monthly_results.csv")
    quarterly = pd.read_csv(PHASE18 / "quarterly_results.csv")
    annual = pd.read_csv(PHASE18 / "annual_results.csv")
    comparison = pd.read_csv(PHASE18 / "model_comparison.csv")
    assert len(monthly) == 6 * 36
    assert len(quarterly) == 6 * 12
    assert len(annual) == 6 * 3
    assert set(comparison["model"]) == {"Control", "BOS", "C1", "C2", "Retest", "Confirm"}

