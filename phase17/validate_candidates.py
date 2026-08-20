"""One-time validation, execution-cost stress, and sequence-risk analysis."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase17.analysis_core import (
    REPORTS,
    RESULTS,
    RESEARCH_END,
    VALIDATION_END,
    apply_spec,
    extended_summary,
    file_sha256,
    max_drawdown,
    max_losing_streak,
    read_trades,
    save_json,
)


VALIDATION_MARKER = RESULTS / "validation_manifest.json"
NQ_DOLLARS_PER_POINT = 20.0
NQ_DOLLARS_PER_TICK = 5.0
COST_SCENARIOS = {
    "Ideal/current": {"slippage_ticks_per_side": 0.0, "round_turn_commission_usd": 0.0},
    "Modest": {"slippage_ticks_per_side": 1.0, "round_turn_commission_usd": 4.50},
    "Conservative": {"slippage_ticks_per_side": 2.0, "round_turn_commission_usd": 8.00},
}


def cost_summary(group: pd.DataFrame, scenario: str, assumptions: dict[str, float]) -> dict[str, object]:
    working = group.sort_values("exit_timestamp", kind="stable").copy()
    slippage = assumptions["slippage_ticks_per_side"] * 2 * NQ_DOLLARS_PER_TICK
    cost_usd = slippage + assumptions["round_turn_commission_usd"]
    risk_usd = working["stop_distance_points"].astype(float) * NQ_DOLLARS_PER_POINT
    working["gross_result_R"] = working["result_R"].astype(float)
    working["result_R"] = working["gross_result_R"] - cost_usd / risk_usd
    metrics = extended_summary(working)
    inverse_risk = (1.0 / risk_usd).sum()
    gross_total = float(working["gross_result_R"].sum())
    break_even = gross_total / inverse_risk if inverse_risk > 0 else np.nan
    return {
        "scenario": scenario,
        "slippage_ticks_per_side": assumptions["slippage_ticks_per_side"],
        "round_turn_commission_usd": assumptions["round_turn_commission_usd"],
        "all_in_cost_usd_per_trade": cost_usd,
        "break_even_all_in_cost_usd_per_trade": break_even,
        **metrics,
    }


def candidate_temporal(candidate_id: str, group: pd.DataFrame, split: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    working = group.copy()
    local = working["entry_timestamp"].dt.tz_localize(None)
    working["month"] = local.dt.to_period("M").astype(str)
    working["quarter"] = local.dt.to_period("Q").astype(str)
    for period_type in ("month", "quarter"):
        for period, period_group in working.groupby(period_type, sort=True):
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "split": split,
                    "period_type": period_type,
                    "period": period,
                    **extended_summary(period_group),
                }
            )
    month_period = local.dt.to_period("M")
    unique_months = pd.period_range(month_period.min(), month_period.max(), freq="M") if len(group) else []
    for window in (3, 6, 12):
        for end in unique_months[window - 1 :]:
            start = end - (window - 1)
            window_group = working.loc[(month_period >= start) & (month_period <= end)]
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "split": split,
                    "period_type": f"rolling_{window}m",
                    "period": f"{start} to {end}",
                    **extended_summary(window_group),
                }
            )
    return rows


def monte_carlo(candidate_id: str, group: pd.DataFrame, *, simulations: int = 5_000) -> list[dict[str, object]]:
    values = group.sort_values("exit_timestamp")["result_R"].astype(float).to_numpy()
    rng = np.random.default_rng(1701)
    totals = np.empty(simulations)
    drawdowns = np.empty(simulations)
    streaks = np.empty(simulations)
    for index in range(simulations):
        sample = rng.choice(values, size=len(values), replace=True)
        totals[index] = sample.sum()
        drawdowns[index] = max_drawdown(sample)
        streaks[index] = max_losing_streak(sample)
    rows = []
    for metric, samples in (
        ("Total R / terminal outcome", totals),
        ("Max DD R", drawdowns),
        ("Longest losing streak", streaks),
    ):
        rows.append(
            {
                "candidate_id": candidate_id,
                "metric": metric,
                "p05": np.quantile(samples, 0.05),
                "p25": np.quantile(samples, 0.25),
                "median": np.quantile(samples, 0.50),
                "p75": np.quantile(samples, 0.75),
                "p95": np.quantile(samples, 0.95),
                "probability_terminal_positive": float(np.mean(totals > 0)),
            }
        )
    return rows


def main() -> None:
    if VALIDATION_MARKER.exists():
        raise RuntimeError(
            "Validation has already been run. Frozen candidates may not be re-tuned or re-run in Phase 17."
        )
    frozen_path = RESULTS / "frozen_candidates.json"
    frozen = json.loads(frozen_path.read_text())
    if frozen.get("validation_examined") is not False:
        raise RuntimeError("Candidate freeze is not sealed")
    frozen_hash = file_sha256(frozen_path)
    features = read_trades(RESULTS / "trade_features.csv")
    research = features.loc[features["entry_timestamp"] < RESEARCH_END]
    validation = features.loc[
        (features["entry_timestamp"] >= RESEARCH_END)
        & (features["entry_timestamp"] < VALIDATION_END)
    ]

    comparison_rows: list[dict[str, object]] = []
    cost_rows: list[dict[str, object]] = []
    temporal_rows: list[dict[str, object]] = []
    survivors: list[tuple[dict[str, object], pd.DataFrame]] = []
    for candidate in frozen["candidates"]:
        research_group = apply_spec(research, candidate)
        validation_group = apply_spec(validation, candidate)
        research_metrics = extended_summary(research_group)
        validation_metrics = extended_summary(validation_group)
        comparison_rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "model": candidate["model"],
                "conditions": json.dumps(candidate["conditions"], sort_keys=True),
                **{f"research_{key}": value for key, value in research_metrics.items()},
                **{f"validation_{key}": value for key, value in validation_metrics.items()},
                "avg_R_degradation": validation_metrics["avg_R"] - research_metrics["avg_R"],
                "PF_degradation": validation_metrics["profit_factor"] - research_metrics["profit_factor"],
            }
        )
        candidate_costs: dict[tuple[str, str], dict[str, object]] = {}
        for split_name, group in (("Research", research_group), ("Validation", validation_group)):
            for scenario, assumptions in COST_SCENARIOS.items():
                result = cost_summary(group, scenario, assumptions)
                candidate_costs[(split_name, scenario)] = result
                cost_rows.append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "model": candidate["model"],
                        "split": split_name,
                        **result,
                    }
                )
            temporal_rows.extend(candidate_temporal(candidate["candidate_id"], group, split_name))
        modest_validation = candidate_costs[("Validation", "Modest")]
        survives = (
            validation_metrics["N"] >= 50
            and validation_metrics["avg_R"] > 0
            and validation_metrics["profit_factor"] > 1
            and modest_validation["avg_R"] > 0
            and research_metrics["avg_R"] > 0
        )
        if survives:
            survivors.append((candidate, validation_group))

    comparison = pd.DataFrame(comparison_rows)
    comparison.to_csv(RESULTS / "candidate_validation.csv", index=False)
    pd.DataFrame(cost_rows).to_csv(RESULTS / "cost_stress.csv", index=False)
    pd.DataFrame(temporal_rows).to_csv(RESULTS / "candidate_temporal.csv", index=False)
    mc_rows: list[dict[str, object]] = []
    for candidate, group in survivors:
        mc_rows.extend(monte_carlo(str(candidate["candidate_id"]), group))
    pd.DataFrame(
        mc_rows,
        columns=[
            "candidate_id",
            "metric",
            "p05",
            "p25",
            "median",
            "p75",
            "p95",
            "probability_terminal_positive",
        ],
    ).to_csv(RESULTS / "monte_carlo.csv", index=False)
    save_json(
        VALIDATION_MARKER,
        {
            "status": "COMPLETE",
            "frozen_candidates_sha256": frozen_hash,
            "candidate_count": len(frozen["candidates"]),
            "survivor_count": len(survivors),
            "validation_start": str(RESEARCH_END),
            "validation_end_exclusive": str(VALIDATION_END),
            "validation_was_run_once": True,
            "cost_assumptions": COST_SCENARIOS,
        },
    )
    print("ONE-TIME VALIDATION: COMPLETE")
    if comparison.empty:
        print("No frozen candidates to validate")
    else:
        print(
            comparison[
                [
                    "candidate_id",
                    "model",
                    "research_N",
                    "research_avg_R",
                    "research_profit_factor",
                    "validation_N",
                    "validation_avg_R",
                    "validation_total_R",
                    "validation_profit_factor",
                    "validation_max_drawdown_R",
                ]
            ].to_string(index=False)
        )
    print(f"MONTE CARLO SURVIVORS: {len(survivors)}")


if __name__ == "__main__":
    main()

