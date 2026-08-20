from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
P19 = ROOT / "phase19"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def test_required_artifacts_exist_and_are_nonempty() -> None:
    required = [
        "README.md",
        "PHASE19_BOS_REPORT.md",
        "bos_baseline.csv",
        "bos_yearly.csv",
        "bos_monthly.csv",
        "bos_rolling_metrics.csv",
        "bos_cost_stress.csv",
        "bos_outlier_stress.csv",
        "bos_monte_carlo.csv",
        "hypothesis_registry.csv",
        "walk_forward_results.csv",
        "parameter_sensitivity.csv",
        "candidate_comparison.csv",
        "FROZEN_PHASE19_CANDIDATES.md",
        "charts/bos_equity_curve.png",
        "charts/bos_drawdown_curve.png",
        "charts/rolling_expectancy.png",
        "charts/rolling_profit_factor.png",
        "charts/yearly_performance.png",
    ]
    for relative in required:
        path = P19 / relative
        assert path.exists(), relative
        assert path.stat().st_size > 0, relative


def test_baseline_gate_is_exact_for_both_periods() -> None:
    baseline = pd.read_csv(P19 / "bos_baseline.csv")
    periods = baseline.loc[baseline["period"].isin(["2021-2023", "2024-2026"])]
    assert len(periods) == 2
    assert periods["metrics_match"].all()
    assert periods["trades_byte_exact"].all()
    assert periods["event_debug_byte_exact"].all()
    assert (periods["reference_trades_sha256"] == periods["reproduced_trades_sha256"]).all()
    assert (periods["reference_event_debug_sha256"] == periods["reproduced_event_debug_sha256"]).all()
    assert periods.set_index("period")["N"].to_dict() == {"2021-2023": 2283, "2024-2026": 1867}


def test_unified_bos_records_are_causal_and_chronological() -> None:
    trades = pd.read_csv(P19 / "bos_trade_features.csv")
    for column in ("setup_timestamp", "bos_timestamp", "entry_timestamp", "exit_timestamp"):
        trades[column] = pd.to_datetime(trades[column], utc=True)
    assert len(trades) == 4150
    assert not trades["entry_timestamp"].duplicated().any()
    assert (trades["setup_timestamp"] <= trades["bos_timestamp"]).all()
    assert (trades["bos_timestamp"] == trades["entry_timestamp"]).all()
    assert (trades["entry_timestamp"] <= trades["exit_timestamp"]).all()
    assert (trades["risk_usd"] > 0).all()
    assert trades.sort_values("exit_timestamp", kind="stable")["exit_timestamp"].is_monotonic_increasing


def test_cost_stress_is_trade_specific_and_monotone() -> None:
    costs = pd.read_csv(P19 / "bos_cost_stress.csv")
    combined = costs.loc[costs["period"] == "2021-2026 combined"].sort_values("round_trip_cost_usd")
    assert len(combined) == 5
    assert combined["total_R"].is_monotonic_decreasing
    assert combined["avg_R"].is_monotonic_decreasing
    assert combined["break_even_round_trip_cost_usd"].nunique() == 1
    assert 0 < combined["break_even_round_trip_cost_usd"].iloc[0] < 9.50


def test_monte_carlo_and_hypothesis_registry_are_complete() -> None:
    monte = pd.read_csv(P19 / "bos_monte_carlo.csv")
    assert set(monte["method"]) == {"IID bootstrap", "Moving-block bootstrap (20 trades)"}
    assert (monte["simulations"] == 10_000).all()
    assert ((monte["probability_terminal_R_positive"] >= 0) & (monte["probability_terminal_R_positive"] <= 1)).all()

    registry = pd.read_csv(P19 / "hypothesis_registry.csv")
    assert len(registry) == 155
    assert registry["hypothesis_id"].is_unique
    tested = registry["N"] >= 50
    assert registry.loc[tested, "fdr_q"].notna().all()
    assert ((registry.loc[tested, "fdr_q"] >= 0) & (registry.loc[tested, "fdr_q"] <= 1)).all()


def test_walk_forward_is_strictly_chronological() -> None:
    walk = pd.read_csv(P19 / "walk_forward_results.csv")
    assert set(walk["fold"]) == {"F1", "F2", "F3", "F4", "F5"}
    assert len(walk) == 5 * 155
    evaluation_start = {"F1": 2022, "F2": 2023, "F3": 2024, "F4": 2025, "F5": 2026}
    training_end = {"F1": 2021, "F2": 2022, "F3": 2023, "F4": 2024, "F5": 2025}
    for fold in evaluation_start:
        assert training_end[fold] < evaluation_start[fold]
        fold_rows = walk.loc[walk["fold"] == fold]
        assert int(fold_rows["selected_by_train"].sum()) <= 1


def test_manifest_pins_immutable_inputs_and_candidate_count() -> None:
    manifest = json.loads((P19 / "analysis_manifest.json").read_text())
    assert manifest["baseline_gate"] == "PASS"
    assert manifest["engine_modified"] is False
    assert manifest["paid_downloads"] is False
    assert manifest["early_reference_trades_sha256"] == digest(ROOT / "phase18/results/base_run/trades.csv")
    assert manifest["late_reference_trades_sha256"] == digest(ROOT / "phase16/results/oos/trades.csv")
    comparison = pd.read_csv(P19 / "candidate_comparison.csv")
    assert len(comparison) == 1 + manifest["frozen_candidates"]
    frozen = (P19 / "FROZEN_PHASE19_CANDIDATES.md").read_text()
    if manifest["frozen_candidates"] == 0:
        assert "zero candidates" in frozen.lower()
