"""Research-only hypothesis evaluation and immutable candidate freeze.

This process never selects on rows dated 2025-07-01 or later.  Validation is a
separate executable which requires the frozen JSON produced here.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from phase17.analysis_core import (
    DIMENSIONS,
    INTERSECTIONS,
    MIN_MEANINGFUL_N,
    MODELS,
    REPORTS,
    RESULTS,
    benjamini_hochberg,
    bootstrap_expectancy,
    extended_summary,
    normal_one_sided_p,
    read_trades,
    save_json,
)


RESEARCH_START = pd.Timestamp("2024-01-01", tz="America/Chicago")
RESEARCH_END = pd.Timestamp("2025-07-01", tz="America/Chicago")


def condition_group(frame: pd.DataFrame, conditions: list[dict[str, object]]) -> pd.DataFrame:
    group = frame
    for condition in conditions:
        group = group.loc[group[str(condition["feature"])] == condition["value"]]
    return group


def robustness(group: pd.DataFrame, seed: int) -> dict[str, object]:
    ordered = group.sort_values("exit_timestamp", kind="stable")
    values = ordered["result_R"].astype(float).to_numpy()
    probability, boot_low, boot_high = bootstrap_expectancy(values, samples=2_000, seed=seed)
    midpoint = RESEARCH_START + (RESEARCH_END - RESEARCH_START) / 2
    first = ordered.loc[ordered["entry_timestamp"] < midpoint]
    second = ordered.loc[ordered["entry_timestamp"] >= midpoint]
    remove_five = ordered.nlargest(min(5, len(ordered)), "result_R").index
    without_five = ordered.drop(remove_five)
    month = ordered["entry_timestamp"].dt.tz_localize(None).dt.to_period("M").astype(str)
    month_totals = ordered.assign(_month=month).groupby("_month")["result_R"].sum()
    best_month = str(month_totals.idxmax()) if len(month_totals) else ""
    without_best_month = ordered.loc[month != best_month] if best_month else ordered
    quarter = ordered["entry_timestamp"].dt.tz_localize(None).dt.to_period("Q").astype(str)
    quarter_totals = ordered.assign(_quarter=quarter).groupby("_quarter")["result_R"].sum()
    month_sign = month_totals < 0
    longest_losing_months = current = 0
    for losing in month_sign.tolist():
        current = current + 1 if losing else 0
        longest_losing_months = max(longest_losing_months, current)
    by_year = ordered.assign(
        _year=ordered["entry_timestamp"].dt.strftime("%Y")
    ).groupby("_year")["result_R"].agg(["count", "mean", "sum"])
    return {
        "bootstrap_probability_positive": probability,
        "bootstrap_ci95_low_R": boot_low,
        "bootstrap_ci95_high_R": boot_high,
        "first_half_N": len(first),
        "first_half_avg_R": first["result_R"].mean() if len(first) else np.nan,
        "first_half_total_R": first["result_R"].sum(),
        "second_half_N": len(second),
        "second_half_avg_R": second["result_R"].mean() if len(second) else np.nan,
        "second_half_total_R": second["result_R"].sum(),
        "without_best_5_total_R": without_five["result_R"].sum(),
        "best_month": best_month,
        "without_best_month_total_R": without_best_month["result_R"].sum(),
        "positive_month_pct": 100 * float((month_totals > 0).mean()) if len(month_totals) else np.nan,
        "positive_quarter_pct": 100 * float((quarter_totals > 0).mean()) if len(quarter_totals) else np.nan,
        "best_quarter": str(quarter_totals.idxmax()) if len(quarter_totals) else "",
        "best_quarter_R": float(quarter_totals.max()) if len(quarter_totals) else np.nan,
        "worst_quarter": str(quarter_totals.idxmin()) if len(quarter_totals) else "",
        "worst_quarter_R": float(quarter_totals.min()) if len(quarter_totals) else np.nan,
        "longest_losing_months": longest_losing_months,
        "yearly_results": json.dumps(by_year.round(6).to_dict(orient="index"), sort_keys=True),
    }


def hypothesis_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    # These are the pre-specified maps requested by the research plan, not a
    # combinatorial search over numeric thresholds.
    for model in MODELS:
        for dimension, (feature, buckets) in DIMENSIONS.items():
            for bucket in buckets:
                specs.append(
                    {
                        "model": model,
                        "dimension": dimension,
                        "condition": bucket,
                        "conditions": [{"feature": feature, "value": bucket}],
                    }
                )
        for left_name, right_name in INTERSECTIONS:
            left_feature, left_values = DIMENSIONS[left_name]
            right_feature, right_values = DIMENSIONS[right_name]
            for left in left_values:
                for right in right_values:
                    specs.append(
                        {
                            "model": model,
                            "dimension": f"{left_name} x {right_name}",
                            "condition": f"{left} | {right}",
                            "conditions": [
                                {"feature": left_feature, "value": left},
                                {"feature": right_feature, "value": right},
                            ],
                        }
                    )
    return specs


def evaluate(research: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for number, spec in enumerate(hypothesis_specs(), start=1):
        model_frame = research.loc[research["model"] == spec["model"]]
        group = condition_group(model_frame, spec["conditions"])
        metrics = extended_summary(group)
        row = {
            "hypothesis_id": f"H{number:04d}",
            "model": spec["model"],
            "dimension": spec["dimension"],
            "condition": spec["condition"],
            "conditions_json": json.dumps(spec["conditions"], sort_keys=True),
            **metrics,
        }
        row["one_sided_p"] = normal_one_sided_p(float(row["avg_R"]), float(row["sem_R"]))
        if int(row["N"]) >= MIN_MEANINGFUL_N and float(row["avg_R"]) > 0:
            row.update(robustness(group, seed=17 + number))
        rows.append(row)
    result = pd.DataFrame(rows)
    tested = result["N"] >= MIN_MEANINGFUL_N
    result["fdr_q"] = np.nan
    result.loc[tested, "fdr_q"] = benjamini_hochberg(result.loc[tested, "one_sided_p"])
    result["evidence_label"] = "DESCRIPTIVE PATTERN"
    interesting = (
        tested
        & (result["avg_R"] > 0)
        & (result["one_sided_p"] < 0.05)
        & (result["bootstrap_probability_positive"].fillna(0) >= 0.95)
    )
    result.loc[interesting, "evidence_label"] = "STATISTICALLY INTERESTING"
    robust = (
        interesting
        & (result["fdr_q"] <= 0.10)
        & (result["N"] >= 100)
        & (result["first_half_total_R"].fillna(-np.inf) > 0)
        & (result["second_half_total_R"].fillna(-np.inf) > 0)
        & (result["without_best_5_total_R"].fillna(-np.inf) > 0)
        & (result["without_best_month_total_R"].fillna(-np.inf) > 0)
        & (result["positive_month_pct"].fillna(0) >= 55)
    )
    result.loc[robust, "evidence_label"] = "ROBUST CANDIDATE EDGE"
    return result


def choose_candidates(hypotheses: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    eligible = hypotheses.loc[
        (hypotheses["N"] >= 100)
        & (hypotheses["avg_R"] > 0)
        & (~hypotheses["dimension"].isin(["date_third", "trend_state"]))
    ].copy()
    robust = eligible.loc[eligible["evidence_label"] == "ROBUST CANDIDATE EDGE"]
    interesting = eligible.loc[
        (eligible["evidence_label"] == "STATISTICALLY INTERESTING")
        & (eligible["first_half_total_R"] > 0)
        & (eligible["second_half_total_R"] > 0)
        & (eligible["without_best_5_total_R"] > 0)
        & (eligible["without_best_month_total_R"] > 0)
    ]
    stable_descriptive = eligible.loc[
        (eligible["bootstrap_probability_positive"] >= 0.80)
        & (eligible["first_half_total_R"] > 0)
        & (eligible["second_half_total_R"] > 0)
        & (eligible["without_best_5_total_R"] > 0)
        & (eligible["without_best_month_total_R"] > 0)
        & (eligible["positive_month_pct"] >= 50)
    ]
    if len(robust):
        pool, basis = robust, "FDR-controlled robust candidates"
    elif len(interesting):
        pool, basis = interesting, "uncorrected statistically interesting candidates; none passed FDR"
    else:
        pool, basis = stable_descriptive, "stable descriptive candidates; none achieved statistical significance"
    if pool.empty:
        return pool, "No candidate met the minimum predeclared stability screen"
    pool = pool.assign(
        _rank=pool["avg_R"] * np.sqrt(pool["N"]) * (pool["positive_month_pct"] / 100)
    ).sort_values(["_rank", "N"], ascending=False)
    selected: list[int] = []
    seen_models: set[str] = set()
    for index, row in pool.iterrows():
        # Freeze at most one rule per base model. This prevents overlapping
        # versions of the same research pattern from masquerading as separate
        # discoveries. No validation result influences this choice.
        model = str(row["model"])
        if model in seen_models:
            continue
        selected.append(index)
        seen_models.add(model)
        if len(selected) == 3:
            break
    return pool.loc[selected].drop(columns="_rank"), basis


def freeze(selected: pd.DataFrame, basis: str, tested_count: int) -> None:
    candidates: list[dict[str, object]] = []
    for number, (_, row) in enumerate(selected.iterrows(), start=1):
        candidates.append(
            {
                "candidate_id": f"C{number}",
                "model": row["model"],
                "conditions": json.loads(row["conditions_json"]),
                "research_hypothesis_id": row["hypothesis_id"],
                "research_evidence_label": row["evidence_label"],
                "research_N": int(row["N"]),
                "research_avg_R": float(row["avg_R"]),
                "research_total_R": float(row["total_R"]),
                "research_profit_factor": float(row["profit_factor"]),
                "research_max_drawdown_R": float(row["max_drawdown_R"]),
                "research_fdr_q": None if pd.isna(row["fdr_q"]) else float(row["fdr_q"]),
                "research_bootstrap_probability_positive": float(row["bootstrap_probability_positive"]),
            }
        )
    payload = {
        "research_window": "2024-01-01 through 2025-06-30 inclusive",
        "validation_window": "2025-07-01 through 2026-06-26 inclusive",
        "hypotheses_with_adequate_samples": tested_count,
        "selection_basis": basis,
        "validation_examined": False,
        "candidates": candidates,
    }
    save_json(RESULTS / "frozen_candidates.json", payload)
    lines = [
        "# Frozen Phase 17 candidates",
        "",
        "This file was written from the research segment only, before the separate validation executable was run.",
        "",
        f"- Research: 2024-01-01 through 2025-06-30 inclusive",
        f"- Validation (sealed at freeze time): 2025-07-01 through 2026-06-26 inclusive",
        f"- Adequately sampled hypotheses tested: {tested_count}",
        f"- Selection basis: {basis}",
        "- Frozen parameters: unchanged from Phase 16",
        "",
    ]
    if not candidates:
        lines.append("No rule met the predeclared minimum candidate screen. Validation will record an empty candidate set.")
    for candidate in candidates:
        condition = " AND ".join(
            f"`{item['feature']} = {item['value']}`" for item in candidate["conditions"]
        )
        lines.extend(
            [
                f"## {candidate['candidate_id']} — {candidate['model']}",
                "",
                f"Rule: {condition}",
                "",
                f"Research N {candidate['research_N']}; Avg R {candidate['research_avg_R']:.4f}; "
                f"Total R {candidate['research_total_R']:.2f}; PF {candidate['research_profit_factor']:.3f}; "
                f"Max DD {candidate['research_max_drawdown_R']:.2f}R.",
                "",
            ]
        )
    (REPORTS / "FROZEN_CANDIDATES.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    features = read_trades(RESULTS / "trade_features.csv")
    research = features.loc[
        (features["entry_timestamp"] >= RESEARCH_START)
        & (features["entry_timestamp"] < RESEARCH_END)
    ].copy()
    hypotheses = evaluate(research)
    hypotheses.to_csv(RESULTS / "research_hypotheses.csv", index=False)
    selected, basis = choose_candidates(hypotheses)
    tested_count = int((hypotheses["N"] >= MIN_MEANINGFUL_N).sum())
    freeze(selected, basis, tested_count)
    print(f"HYPOTHESES TESTED (N>={MIN_MEANINGFUL_N}): {tested_count}")
    print(f"FROZEN CANDIDATES: {len(selected)}")
    print(f"SELECTION BASIS: {basis}")
    if len(selected):
        print(selected[["hypothesis_id", "model", "dimension", "condition", "N", "avg_R", "total_R", "profit_factor", "fdr_q", "evidence_label"]].to_string(index=False))


if __name__ == "__main__":
    main()
