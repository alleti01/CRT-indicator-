"""Baseline gate and descriptive Phase 17 artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase17.analysis_core import (
    MODELS,
    P16_RESULTS,
    REPORTS,
    RESULTS,
    build_trade_features,
    edge_map,
    file_sha256,
    prepare_market_features,
    read_trades,
    temporal_results,
)


ROOT = Path(__file__).resolve().parents[1]
BASELINE_RUN = RESULTS / "baseline_run"
DATA = ROOT / "phase16" / "data" / "processed" / "nq_5m.csv"


def baseline_gate() -> pd.DataFrame:
    reference_path = P16_RESULTS / "model_comparison.csv"
    reproduced_path = BASELINE_RUN / "model_comparison.csv"
    if not reproduced_path.exists():
        raise RuntimeError(
            "Phase 17 baseline run is missing. Run the frozen Phase 16 engine into "
            "phase17/results/baseline_run before research."
        )
    reference = pd.read_csv(reference_path)
    reproduced = pd.read_csv(reproduced_path)
    key = "model"
    if list(reference.columns) != list(reproduced.columns):
        raise RuntimeError("BASELINE REPRODUCTION FAIL: metric columns differ")
    reference = reference.set_index(key).loc[list(MODELS)]
    reproduced = reproduced.set_index(key).loc[list(MODELS)]
    exact = reference.equals(reproduced)
    rows: list[dict[str, object]] = []
    for model in MODELS:
        row: dict[str, object] = {"model": model, "baseline_match": bool(exact)}
        for column in reference.columns:
            row[column] = reproduced.loc[model, column]
            row[f"reference_{column}"] = reference.loc[model, column]
            row[f"delta_{column}"] = reproduced.loc[model, column] - reference.loc[model, column]
        rows.append(row)
    baseline = pd.DataFrame(rows)
    baseline.to_csv(RESULTS / "baseline.csv", index=False)
    if not exact:
        differences = reference.compare(reproduced)
        raise RuntimeError(f"BASELINE REPRODUCTION FAIL:\n{differences}")
    return baseline


def trade_forensics(features: pd.DataFrame) -> pd.DataFrame:
    numeric = [
        "score",
        "normalized_atr",
        "stop_distance_points",
        "stop_distance_atr",
        "distance_from_crt_atr",
        "time_since_setup_bars",
        "time_since_bos_bars",
        "time_since_retest_bars",
        "body_to_atr",
        "volume_zscore",
    ]
    rows: list[dict[str, object]] = []
    for model in MODELS:
        model_group = features.loc[features["model"] == model]
        for outcome in ("Win", "Loss", "Flat"):
            group = model_group.loc[model_group["outcome"] == outcome]
            row: dict[str, object] = {"model": model, "outcome": outcome, "N": len(group)}
            for column in numeric:
                values = group[column].astype(float)
                row[f"{column}_mean"] = values.mean()
                row[f"{column}_median"] = values.median()
            rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    baseline = baseline_gate()
    trades = read_trades(BASELINE_RUN / "trades.csv")
    market = prepare_market_features(DATA)
    features = build_trade_features(trades, market)
    features.to_csv(RESULTS / "trade_features.csv", index=False)

    diagnostic, intersections = edge_map(features)
    diagnostic.to_csv(RESULTS / "diagnostic_edge_map.csv", index=False)
    intersections.to_csv(RESULTS / "intersection_edge_map.csv", index=False)
    calendar, rolling = temporal_results(features)
    calendar.to_csv(RESULTS / "temporal_calendar.csv", index=False)
    rolling.to_csv(RESULTS / "temporal_rolling.csv", index=False)
    trade_forensics(features).to_csv(RESULTS / "trade_forensics.csv", index=False)

    manifest = {
        "baseline_reproduction": "PASS",
        "reference_hash": file_sha256(P16_RESULTS / "model_comparison.csv"),
        "reproduced_hash": file_sha256(BASELINE_RUN / "model_comparison.csv"),
        "phase16_trades_hash": file_sha256(P16_RESULTS / "trades.csv"),
        "phase17_trades_hash": file_sha256(BASELINE_RUN / "trades.csv"),
        "data_hash": file_sha256(DATA),
        "trade_rows": len(features),
        "market_rows": len(market),
        "research_trades": int((features["split"] == "Research").sum()),
        "validation_trades": int((features["split"] == "Validation").sum()),
        "outside_trades": int((features["split"] == "Outside").sum()),
        "entry_feature_missing": {
            column: int(features[column].isna().sum())
            for column in (
                "atr",
                "volatility_regime",
                "trend_regime",
                "stop_distance_points",
                "distance_from_crt_atr",
            )
        },
    }
    (RESULTS / "analysis_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    (REPORTS / "REGIME_DEFINITIONS.md").write_text(
        """# Phase 17 causal regime definitions

All timestamps and regimes use `America/Chicago`. Values are attached at the
trade's entry-bar close, when the frozen engine enters.

- **Volatility:** ATR(14) divided by close. Low/medium/high are classified
  against the 33rd/67th percentiles of the preceding 17,280 five-minute bars
  (about 60 complete futures sessions), with a 1,000-bar minimum. Thresholds
  are shifted one bar, so the current bar does not classify itself.
- **Trend:** the already-validated Phase 16 previous-closed 60-minute HTF
  regime. It uses EMA(20), EMA(50), ATR(14), a 0.10 ATR neutral-width threshold,
  close/EMA alignment, and the prior fast-EMA slope. Values are bullish trend,
  bearish trend, or range/chop. No incomplete 60-minute bar is used.
- **Session:** the frozen exchange-local Phase 16 buckets. Report labels map
  Opening to Open, Morning to MidAM, and Afternoon to PM only for readability.
- **CRT distance:** absolute entry-price distance from the prior five-minute
  CRT boundary already calculated by Phase 16 (`crt_low` for longs and
  `crt_high` for shorts), normalized by entry ATR. This is descriptive and was
  not part of the frozen entry decision.

No future-derived outcome or bar is used in `trade_features.csv`.
"""
    )
    print("BASELINE REPRODUCTION: PASS")
    print(baseline[["model", "N", "total_R", "profit_factor", "baseline_match"]].to_string(index=False))
    print(f"Trade features: {len(features)} rows")


if __name__ == "__main__":
    main()

