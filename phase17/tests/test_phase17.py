from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase17.analysis_core import RESULTS, P16_RESULTS, apply_spec, file_sha256, read_trades


def test_baseline_is_exact_phase16_reference() -> None:
    reference = pd.read_csv(P16_RESULTS / "model_comparison.csv")
    reproduced = pd.read_csv(RESULTS / "baseline_run" / "model_comparison.csv")
    assert reference.equals(reproduced)
    baseline = pd.read_csv(RESULTS / "baseline.csv")
    assert baseline["baseline_match"].all()
    assert (baseline.filter(like="delta_").fillna(0) == 0).all().all()


def test_phase16_trade_export_was_not_changed() -> None:
    manifest = json.loads((RESULTS / "analysis_manifest.json").read_text())
    assert file_sha256(P16_RESULTS / "trades.csv") == manifest["phase16_trades_hash"]
    assert manifest["phase16_trades_hash"] == manifest["phase17_trades_hash"]


def test_entry_features_and_split_are_complete() -> None:
    features = read_trades(RESULTS / "trade_features.csv")
    assert len(features) == 6363
    assert set(features["split"]) == {"Research", "Validation"}
    assert not features[
        [
            "atr",
            "volatility_regime",
            "trend_regime",
            "stop_distance_points",
            "distance_from_crt_atr",
        ]
    ].isna().any().any()
    research = features.loc[features["split"] == "Research", "entry_timestamp"]
    validation = features.loc[features["split"] == "Validation", "entry_timestamp"]
    boundary = pd.Timestamp("2025-07-01", tz="America/Chicago")
    assert research.max() < boundary
    assert validation.min() >= boundary


def test_frozen_candidates_match_one_time_validation_counts() -> None:
    frozen = json.loads((RESULTS / "frozen_candidates.json").read_text())
    manifest = json.loads((RESULTS / "validation_manifest.json").read_text())
    assert manifest["frozen_candidates_sha256"] == file_sha256(RESULTS / "frozen_candidates.json")
    features = read_trades(RESULTS / "trade_features.csv")
    comparison = pd.read_csv(RESULTS / "candidate_validation.csv").set_index("candidate_id")
    for candidate in frozen["candidates"]:
        group = apply_spec(features, candidate)
        research_count = int((group["split"] == "Research").sum())
        validation_count = int((group["split"] == "Validation").sum())
        row = comparison.loc[candidate["candidate_id"]]
        assert research_count == row["research_N"]
        assert validation_count == row["validation_N"]


def test_cost_scenarios_degrade_monotonically() -> None:
    costs = pd.read_csv(RESULTS / "cost_stress.csv")
    order = ["Ideal/current", "Modest", "Conservative"]
    for (_, _), group in costs.groupby(["candidate_id", "split"]):
        values = group.set_index("scenario").loc[order, "total_R"].to_numpy()
        assert values[0] > values[1] > values[2]


def test_diagnostic_maps_keep_empty_buckets_and_sample_flags() -> None:
    edge = pd.read_csv(RESULTS / "diagnostic_edge_map.csv")
    assert set(edge["model"]) == {"Control", "BOS", "Retest", "Confirm"}
    assert {"70-74", "75-79", "80-84", "85-89", "90-94", "95+"}.issubset(
        set(edge.loc[edge["dimension"] == "score_band", "bucket"])
    )
    assert (edge.loc[edge["N"] < 30, "adequate_sample"] == False).all()  # noqa: E712

