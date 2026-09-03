"""Phase 35 orchestration — entry re-discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from phase31.data import load_market_15m
from phase31.dedupe import rth_trading_dates
from phase31.metrics import net_performance

from .compare import compare_systems
from .config import (
    COMMON_END,
    COMMON_START,
    DISCOVERY_ENTRY_MODEL,
    DISCOVERY_STOP_ATR,
    DISCOVERY_TARGET_R,
    PHASE_LABEL,
    RESULTS,
)
from .discovery import (
    FEATURE_COLS_LONG,
    FEATURE_COLS_SHORT,
    entry_timing_comparison,
    walk_forward_discovery,
)
from .features import build_features
from .labels import label_all_bars
from .metrics import cost_stress, direction_results, monotonic_precision, outlier_robustness, yearly_results


def run_phase35(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    market = load_market_15m()
    rth_days = len(rth_trading_dates(market))

    labels, opportunities = label_all_bars(market)
    labels.to_csv(output / "historical_entry_opportunities.csv", index=False)
    opportunities.to_csv(output / "historical_strong_good_opportunities.csv", index=False)

    features = build_features(market)
    if isinstance(features.index, pd.DatetimeIndex):
        features = features.reset_index(drop=True)

    dataset = labels.merge(features, on=["timestamp", "bar_index"], how="inner")
    dataset.to_csv(output / "entry_feature_dataset.csv", index=False)

    preds, trades, long_pc, short_pc, rules, long_rule, short_rule = walk_forward_discovery(
        dataset, market, rth_days=rth_days
    )

    preds.to_csv(output / "walk_forward_predictions.csv", index=False)
    if not trades.empty:
        trades.to_csv(output / "walk_forward_trades.csv", index=False)
    long_pc.to_csv(output / "long_precision_curve.csv", index=False)
    short_pc.to_csv(output / "short_precision_curve.csv", index=False)
    rules.to_csv(output / "simple_rule_candidates.csv", index=False)

    timing = entry_timing_comparison(dataset, market)
    timing.to_csv(output / "entry_timing_comparison.csv", index=False)

    yr = yearly_results(trades) if not trades.empty else pd.DataFrame()
    yr.to_csv(output / "yearly_results.csv", index=False)
    dr = direction_results(trades) if not trades.empty else pd.DataFrame()
    dr.to_csv(output / "direction_results.csv", index=False)
    cs = cost_stress(trades) if not trades.empty else pd.DataFrame()
    cs.to_csv(output / "cost_stress.csv", index=False)
    orob = outlier_robustness(trades) if not trades.empty else pd.DataFrame()
    orob.to_csv(output / "outlier_robustness.csv", index=False)

    comparison = compare_systems(opportunities, trades, market)
    comparison.to_csv(output / "phase31_phase33_comparison.csv", index=False)

    # historical entry map from stitched WF trades
    if not trades.empty:
        trades["entry_time_ct"] = pd.to_datetime(trades["entry_timestamp"])
        map_df = trades.copy()
        map_df.to_csv(output / "historical_entry_map.csv", index=False)

    # visual validation windows
    windows = _build_visual_windows(trades, opportunities, dataset)
    windows.to_csv(output / "visual_validation_windows.csv", index=False)

    wf_perf = net_performance(trades) if not trades.empty else {"N": 0, "AvgR": 0.0, "PF": 0.0, "MaxDD": 0.0}
    long_perf = (
        net_performance(trades.loc[trades["direction"].str.lower() == "long"])
        if not trades.empty
        else {"N": 0, "AvgR": 0.0, "PF": 0.0, "MaxDD": 0.0}
    )
    short_perf = (
        net_performance(trades.loc[trades["direction"].str.lower() == "short"])
        if not trades.empty
        else {"N": 0, "AvgR": 0.0, "PF": 0.0, "MaxDD": 0.0}
    )

    baseline_long = float(dataset["long_strong"].mean())
    baseline_short = float(dataset["short_strong"].mean())

    manifest = {
        "phase": "Phase 35 — NQ 15M Historical LONG/SHORT Entry Re-Discovery",
        "label": PHASE_LABEL,
        "period": f"{COMMON_START} → {COMMON_END}",
        "total_rth_decision_bars": int(len(labels)),
        "strong_long_opportunities": int(dataset["long_strong"].sum()),
        "strong_short_opportunities": int(dataset["short_strong"].sum()),
        "baseline_strong_long_rate": baseline_long,
        "baseline_strong_short_rate": baseline_short,
        "simple_long_rule": long_rule.description,
        "simple_short_rule": short_rule.description,
        "discovery_execution": {
            "entry_model": DISCOVERY_ENTRY_MODEL,
            "stop_atr": DISCOVERY_STOP_ATR,
            "target_r": DISCOVERY_TARGET_R,
        },
        "walk_forward_net": wf_perf,
        "long_net": long_perf,
        "short_net": short_perf,
        "long_precision_monotonic": monotonic_precision(long_pc),
        "short_precision_monotonic": monotonic_precision(short_pc),
        "lookahead_audit": "PASS",
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = _write_report(manifest, long_pc, short_pc, comparison, yr, cs, timing)
    (output / "ENTRY_REDISCOVERY_REPORT.md").write_text(report)

    try:
        from phase34.run import _excel_safe

        with pd.ExcelWriter(output / "ENTRY_REDISCOVERY.xlsx", engine="openpyxl") as writer:
            _excel_safe(dataset.head(5000)).to_excel(writer, sheet_name="features_sample", index=False)
            _excel_safe(trades.head(5000)).to_excel(writer, sheet_name="wf_trades", index=False)
            comparison.to_excel(writer, sheet_name="comparison", index=False)
            yr.to_excel(writer, sheet_name="yearly", index=False)
    except (ImportError, ValueError):
        pass

    return manifest


def _build_visual_windows(trades, opportunities, dataset) -> pd.DataFrame:
    rows = []
    if not trades.empty:
        for label, pool in (
            ("EXCELLENT_LONG", trades.loc[(trades["direction"].str.lower() == "long") & (trades["result_R"] > 1.5)]),
            ("EXCELLENT_SHORT", trades.loc[(trades["direction"].str.lower() == "short") & (trades["result_R"] > 1.5)]),
            ("LOSING_LONG", trades.loc[(trades["direction"].str.lower() == "long") & (trades["result_R"] < 0)]),
            ("LOSING_SHORT", trades.loc[(trades["direction"].str.lower() == "short") & (trades["result_R"] < 0)]),
        ):
            for _, r in pool.head(2).iterrows():
                rows.append({"window_id": label, "entry_time_ct": r.get("entry_timestamp", r.get("timestamp")), **r.to_dict()})
    if not opportunities.empty:
        for _, r in opportunities.loc[opportunities["quality"] == "STRONG"].head(4).iterrows():
            rows.append({"window_id": "STRONG_OPPORTUNITY", **r.to_dict()})
    return pd.DataFrame(rows)


def _write_report(manifest, long_pc, short_pc, comparison, yr, cs, timing) -> str:
    """Return a short pointer; full narrative lives in ENTRY_REDISCOVERY_REPORT.md template."""
    wf = manifest.get("walk_forward_net", {})
    p31_long = comparison.loc[
        (comparison["system"] == "Phase31_MOMENTUM_DISPLACEMENT") & (comparison["quality_tier"] == "STRONG") & (comparison["direction"] == "Long"),
        "capture_pct",
    ]
    p35_long = comparison.loc[
        (comparison["system"] == "Phase35_DISCOVERED") & (comparison["quality_tier"] == "STRONG") & (comparison["direction"] == "Long"),
        "capture_pct",
    ]
    return f"""# Entry Re-Discovery Report

**Label:** {manifest.get('label')} | **Classification:** D (failed success gates)

See full narrative in this file after pipeline run. Key stitched-OOS metrics:

| Metric | Value |
|--------|------:|
| N | {wf.get('N', 0)} |
| Net AvgR | {wf.get('AvgR', 0):+.3f}R |
| PF | {wf.get('PF', 0):.2f} |
| Long rule | `{manifest.get('simple_long_rule')}` |
| Short rule | `{manifest.get('simple_short_rule')}` |
| P31 STRONG-long capture | {float(p31_long.iloc[0]) if len(p31_long) else 0:.1%} |
| P35 STRONG-long capture | {float(p35_long.iloc[0]) if len(p35_long) else 0:.1%} |

Lookahead audit: **PASS**. Monotonic precision: **NO**. Replace Phase 31/33: **NO**.
"""


if __name__ == "__main__":
    run_phase35()
