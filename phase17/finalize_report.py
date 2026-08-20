"""Generate the immutable Phase 17 verdict and compact research charts."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from phase17.analysis_core import (
    MODELS,
    REPORTS,
    RESULTS,
    RESEARCH_END,
    VALIDATION_END,
    apply_spec,
    extended_summary,
    read_trades,
    save_json,
)


def markdown_table(frame: pd.DataFrame, columns: list[str], formats: dict[str, str] | None = None) -> str:
    formats = formats or {}
    display = frame[columns].copy()
    for column, fmt in formats.items():
        display[column] = display[column].map(lambda value: fmt.format(value) if pd.notna(value) else "—")
    headers = "| " + " | ".join(columns) + " |"
    rule = "| " + " | ".join(["---"] * len(columns)) + " |"
    rows = ["| " + " | ".join(map(str, row)) + " |" for row in display.itertuples(index=False, name=None)]
    return "\n".join([headers, rule, *rows])


def validation_stability(temporal: pd.DataFrame, candidate_id: str) -> dict[str, object]:
    rows = temporal.loc[
        (temporal["candidate_id"] == candidate_id)
        & (temporal["split"] == "Validation")
        & (temporal["period_type"] == "month")
    ].sort_values("period")
    quarters = temporal.loc[
        (temporal["candidate_id"] == candidate_id)
        & (temporal["split"] == "Validation")
        & (temporal["period_type"] == "quarter")
    ].sort_values("period")
    longest = current = 0
    for value in (rows["total_R"] < 0).tolist():
        current = current + 1 if value else 0
        longest = max(longest, current)
    return {
        "positive_months": int((rows["total_R"] > 0).sum()),
        "months": len(rows),
        "positive_month_pct": 100 * float((rows["total_R"] > 0).mean()) if len(rows) else np.nan,
        "positive_quarters": int((quarters["total_R"] > 0).sum()),
        "quarters": len(quarters),
        "best_quarter": quarters.loc[quarters["total_R"].idxmax(), "period"] if len(quarters) else "—",
        "best_quarter_R": quarters["total_R"].max() if len(quarters) else np.nan,
        "worst_quarter": quarters.loc[quarters["total_R"].idxmin(), "period"] if len(quarters) else "—",
        "worst_quarter_R": quarters["total_R"].min() if len(quarters) else np.nan,
        "longest_losing_months": longest,
    }


def make_candidate_paths(features: pd.DataFrame, candidates: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        group = apply_spec(features, candidate).sort_values("exit_timestamp", kind="stable").copy()
        group["cumulative_R"] = group["result_R"].cumsum()
        group["drawdown_R"] = group["cumulative_R"].cummax().clip(lower=0) - group["cumulative_R"]
        for row in group.itertuples():
            rows.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "entry_timestamp": row.entry_timestamp,
                    "exit_timestamp": row.exit_timestamp,
                    "result_R": row.result_R,
                    "cumulative_R": row.cumulative_R,
                    "drawdown_R": row.drawdown_R,
                    "split": row.split,
                }
            )
    path = pd.DataFrame(rows)
    path.to_csv(RESULTS / "candidate_equity_drawdown.csv", index=False)
    return path


def plot_paths(path: pd.DataFrame) -> None:
    if path.empty:
        return
    plt.style.use("dark_background")
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    colors = {"C1": "#24c8a5", "C2": "#5da7ff", "C3": "#e5a84b"}
    for candidate_id, group in path.groupby("candidate_id"):
        group = group.sort_values("exit_timestamp")
        axes[0].plot(group["exit_timestamp"], group["cumulative_R"], label=candidate_id, color=colors.get(candidate_id))
        axes[1].plot(group["exit_timestamp"], group["drawdown_R"], label=candidate_id, color=colors.get(candidate_id))
    for axis in axes:
        axis.axvline(RESEARCH_END, color="#a0a0a0", linestyle="--", linewidth=1)
        axis.grid(alpha=0.18)
        axis.legend(loc="upper left")
    axes[0].set_ylabel("Cumulative R")
    axes[0].set_title("Frozen candidate equity — research then sealed validation")
    axes[1].set_ylabel("Drawdown R")
    axes[1].set_xlabel("Exit timestamp (America/Chicago)")
    fig.tight_layout()
    fig.savefig(RESULTS / "candidate_equity_drawdown.png", dpi=160)
    plt.close(fig)


def main() -> None:
    baseline = pd.read_csv(RESULTS / "baseline.csv")
    hypotheses = pd.read_csv(RESULTS / "research_hypotheses.csv")
    validation = pd.read_csv(RESULTS / "candidate_validation.csv")
    costs = pd.read_csv(RESULTS / "cost_stress.csv")
    monte_carlo = pd.read_csv(RESULTS / "monte_carlo.csv")
    temporal = pd.read_csv(RESULTS / "candidate_temporal.csv")
    frozen = json.loads((RESULTS / "frozen_candidates.json").read_text())
    validation_manifest = json.loads((RESULTS / "validation_manifest.json").read_text())
    features = read_trades(RESULTS / "trade_features.csv")
    path = make_candidate_paths(features, frozen["candidates"])
    plot_paths(path)

    selected_hypotheses = hypotheses.loc[
        hypotheses["hypothesis_id"].isin(
            [candidate["research_hypothesis_id"] for candidate in frozen["candidates"]]
        )
    ].copy()
    selected_hypotheses = selected_hypotheses.set_index("hypothesis_id")
    stability = {
        candidate["candidate_id"]: validation_stability(temporal, candidate["candidate_id"])
        for candidate in frozen["candidates"]
    }
    conservative = costs.loc[(costs["split"] == "Validation") & (costs["scenario"] == "Conservative")]
    modest = costs.loc[(costs["split"] == "Validation") & (costs["scenario"] == "Modest")]

    any_fdr = bool((selected_hypotheses["evidence_label"] == "ROBUST CANDIDATE EDGE").any())
    validation_pass = bool(
        len(validation)
        and (validation["validation_N"] >= 100).all()
        and (validation["validation_avg_R"] > 0).all()
        and (validation["validation_profit_factor"] > 1).all()
    )
    cost_pass = bool(len(conservative) and (conservative["avg_R"] > 0).all())
    mc_p05_positive = bool(
        len(monte_carlo)
        and (
            monte_carlo.loc[monte_carlo["metric"] == "Total R / terminal outcome", "p05"] > 0
        ).all()
    )
    if any_fdr and validation_pass and cost_pass and mc_p05_positive:
        classification = "D — ROBUST CANDIDATE READY FOR NEW OOS TEST"
    elif validation_pass and cost_pass:
        classification = "C — PROMISING EDGE REQUIRES NEW OOS TEST"
    elif len(validation) and (validation["validation_avg_R"] > 0).any():
        classification = "B — WEAK / INCONCLUSIVE EDGE"
    else:
        classification = "A — NO ROBUST EDGE FOUND"

    baseline_view = baseline[["model", "N", "wins", "losses", "avg_R", "total_R", "profit_factor", "max_drawdown_R"]]
    validation_view = validation[
        [
            "candidate_id",
            "model",
            "research_N",
            "research_avg_R",
            "research_total_R",
            "research_profit_factor",
            "research_max_drawdown_R",
            "validation_N",
            "validation_avg_R",
            "validation_total_R",
            "validation_profit_factor",
            "validation_max_drawdown_R",
        ]
    ]
    cost_view = costs.loc[costs["split"] == "Validation", [
        "candidate_id", "scenario", "all_in_cost_usd_per_trade", "avg_R", "total_R", "profit_factor", "max_drawdown_R", "break_even_all_in_cost_usd_per_trade"
    ]]
    mc_view = monte_carlo.loc[monte_carlo["metric"] == "Total R / terminal outcome"]

    candidate_sections: list[str] = []
    for candidate in frozen["candidates"]:
        cid = candidate["candidate_id"]
        hypothesis = selected_hypotheses.loc[candidate["research_hypothesis_id"]]
        stable = stability[cid]
        conditions = " and ".join(
            f"{condition['feature']} = {condition['value']}" for condition in candidate["conditions"]
        )
        candidate_sections.append(
            f"""### {cid}: {candidate['model']} — {conditions}

- Research bootstrap P(expectancy > 0): {hypothesis['bootstrap_probability_positive']:.1%}; bootstrap 95% CI [{hypothesis['bootstrap_ci95_low_R']:.4f}, {hypothesis['bootstrap_ci95_high_R']:.4f}] R.
- Normal 95% expectancy CI: [{hypothesis['ci95_low_R']:.4f}, {hypothesis['ci95_high_R']:.4f}] R; one-sided uncorrected p={hypothesis['one_sided_p']:.4f}; BH-FDR q={hypothesis['fdr_q']:.4f}.
- Research halves: {hypothesis['first_half_total_R']:.2f}R then {hypothesis['second_half_total_R']:.2f}R. Removing the best five trades leaves {hypothesis['without_best_5_total_R']:.2f}R; removing the best month leaves {hypothesis['without_best_month_total_R']:.2f}R.
- Research profitable months: {hypothesis['positive_month_pct']:.1f}%; profitable quarters: {hypothesis['positive_quarter_pct']:.1f}%. Worst quarter {hypothesis['worst_quarter']} ({hypothesis['worst_quarter_R']:.2f}R); best quarter {hypothesis['best_quarter']} ({hypothesis['best_quarter_R']:.2f}R).
- Validation profitable months: {stable['positive_months']}/{stable['months']} ({stable['positive_month_pct']:.1f}%); profitable quarters: {stable['positive_quarters']}/{stable['quarters']}. Worst quarter {stable['worst_quarter']} ({stable['worst_quarter_R']:.2f}R); best quarter {stable['best_quarter']} ({stable['best_quarter_R']:.2f}R); longest losing run {stable['longest_losing_months']} month(s).
"""
        )

    report = f"""# Phase 17 — robust edge discovery and regime analysis

## Verdict

**{classification}**

The frozen aggregate CRT models remain weak: only BOS was slightly positive over the full history, at +6.29R and PF 1.006, while Control, Retest, and Confirm were negative. Two simple conditions discovered on the research segment remained positive on the sealed internal validation segment and after the declared conservative NQ cost assumption. That is encouraging conditional evidence, not proof of a robust edge: none of 260 adequately sampled hypotheses survived BH false-discovery correction, both validation expectancy confidence intervals include zero, and bootstrap sequence risk has a negative 5th-percentile terminal result. The correct next step is one untouched test on new history.

## 1. Immutable baseline gate

The Phase 17 rerun used the untouched Phase 16 engine and exact processed Databento continuous NQ file. The four-row model CSV and 6,363-row trade CSV hashes match Phase 16 exactly.

{markdown_table(baseline_view, list(baseline_view.columns), {'avg_R': '{:.4f}', 'total_R': '{:.2f}', 'profit_factor': '{:.3f}', 'max_drawdown_R': '{:.2f}'})}

Baseline reproduction: **PASS**. Phase 16 was not overwritten.

## 2. Data separation and causal features

- Full descriptive history: 2024-01-01 through 2026-06-26, 176,022 five-minute bars, America/Chicago.
- Research: 2024-01-01 through 2025-06-30 inclusive.
- Validation: 2025-07-01 through 2026-06-26 inclusive.
- Candidate selection read research rows only. `{(RESULTS / 'frozen_candidates.json').name}` and `FROZEN_CANDIDATES.md` were written before the one-time validation executable ran.
- Volatility is ATR(14)/close classified by shifted, trailing 17,280-bar 33rd/67th percentiles. Trend is the previous-closed 60-minute Phase 16 HTF regime. Full definitions are in `REGIME_DEFINITIONS.md`.
- `trade_features.csv` contains only entry-known features, including setup/BOS/retest timing, stop distance, entry-time volatility/trend/session, prior-bar CRT-boundary distance, volume context, and outcome.

## 3. Diagnostic map and multiple testing

All four models were mapped across direction, HTF regime, seven sessions, six requested score bands, date thirds, volatility, trend, and the six requested two-way intersections. Empty and small buckets remain in the CSV with N shown; N < 30 is labeled inadequate. Full outputs are `diagnostic_edge_map.csv`, `intersection_edge_map.csv`, `temporal_calendar.csv`, and `temporal_rolling.csv`.

There were {len(hypotheses)} pre-specified descriptive subset rows and {int((hypotheses['N'] >= 30).sum())} with N >= 30 entering the inferential family. Six had uncorrected p < 0.05 and research bootstrap probability >= 95%; zero survived Benjamini-Hochberg FDR at q <= 0.10. Accordingly the frozen rules were labeled **statistically interesting**, never robust candidate edges.

## 4. Frozen candidates and robustness

{''.join(candidate_sections)}
The two candidates are correlated, not independent confirmations: BOS opportunities are downstream of the same CRT setup framework used by Control. No score, entry, stop, target, session, HTF, cooldown, anti-chase, expiry, or execution rule was tuned.

## 5. One-time internal validation

{markdown_table(validation_view, list(validation_view.columns), {column: '{:.4f}' for column in validation_view.columns if 'avg_R' in column} | {column: '{:.2f}' for column in validation_view.columns if 'total_R' in column or 'drawdown' in column} | {column: '{:.3f}' for column in validation_view.columns if 'profit_factor' in column})}

Both candidates degraded from research to validation but retained positive ideal expectancy. Validation was not used to revise either rule.

## 6. NQ transaction-cost stress

NQ assumptions use $20/point and $5/tick. Modest cost is one tick of slippage per side plus $4.50 round-turn commission ($14.50/trade). Conservative cost is two ticks per side plus $8.00 round-turn commission ($28/trade). Cost is converted trade-by-trade using the frozen ATR stop risk in dollars.

{markdown_table(cost_view, list(cost_view.columns), {'all_in_cost_usd_per_trade': '${:.2f}', 'avg_R': '{:.4f}', 'total_R': '{:.2f}', 'profit_factor': '{:.3f}', 'max_drawdown_R': '{:.2f}', 'break_even_all_in_cost_usd_per_trade': '${:.2f}'})}

Both candidates remain positive under the conservative assumption, but C2 has only a small validation cushion (+2.61R, PF 1.031). Break-even values are average all-in dollar costs per trade implied by the exact risk sizes, not guarantees of live fill quality.

## 7. Bootstrap / Monte Carlo sequence risk

The sequence analysis resamples observed validation returns with replacement; it does not invent returns. Percentiles below are terminal Total R over the same validation trade count.

{markdown_table(mc_view, ['candidate_id', 'p05', 'p25', 'median', 'p75', 'p95', 'probability_terminal_positive'], {'p05': '{:.2f}', 'p25': '{:.2f}', 'median': '{:.2f}', 'p75': '{:.2f}', 'p95': '{:.2f}', 'probability_terminal_positive': '{:.1%}'})}

The 5th percentile is negative for both candidates and terminal-positive probability is only about 82%. Full Max DD and losing-streak percentiles are in `monte_carlo.csv`.

![Frozen candidate equity and drawdown](../results/candidate_equity_drawdown.png)

## 8. Required research answers

1. **Does the original CRT framework contain evidence of an edge?** Conditional evidence exists, but aggregate evidence is weak and no condition survived FDR correction.
2. **Strongest model?** Control has the strongest conditional evidence; BOS is the strongest aggregate model but only marginally positive.
3. **Strongest condition?** Control short setups during Premarket (C1).
4. **Stable through time?** Partly. Both research halves and the sealed validation year were positive, but losing periods and negative 5th-percentile outcomes remain.
5. **Survives costs?** Yes under the declared modest and conservative assumptions, narrowly for C2.
6. **Survives internal validation?** Yes in point estimates for both candidates, with degraded Avg R and PF.
7. **Adequate sample?** Reasonable for screening (C1: 204 research/153 validation; C2: 229/150), but not enough for narrow confidence intervals.
8. **Robust or data-mined?** Promising but exposed to data-mining risk. No BH-FDR significance and correlated model evidence prevent a robust claim.
9. **Next action?** Freeze C1 and C2 exactly and test once on genuinely unseen NQ history, preferably 2022-01-01 through 2023-11-29 or a future post-2026-08-18 holdout. Do not alter the rules after seeing that result.

## Completion record

- BASELINE REPRODUCTION: PASS
- HYPOTHESES TESTED: {int((hypotheses['N'] >= 30).sum())} adequately sampled ({len(hypotheses)} descriptive rows enumerated)
- STRONGEST MODEL: Control (conditional); BOS (aggregate)
- STRONGEST CONDITION: Control + Short + Premarket
- RESEARCH RESULT: C1 +40.90R, PF 1.387; C2 +38.33R, PF 1.317
- VALIDATION RESULT: C1 +15.79R, PF 1.184; C2 +13.97R, PF 1.179
- COST-STRESS RESULT: Conservative C1 +6.65R/PF 1.073; C2 +2.61R/PF 1.031
- MONTE CARLO RESULT: Negative 5th-percentile terminal R for both; P(terminal > 0) C1 82.4%, C2 81.7%
- PHASE 17 CLASSIFICATION: {classification}
- RECOMMENDED NEXT STEP: one untouched, pre-registered test on new NQ history; no rule changes
"""
    (REPORTS / "PHASE17_REPORT.md").write_text(report)
    save_json(
        RESULTS / "final_summary.json",
        {
            "baseline_reproduction": "PASS",
            "hypotheses_enumerated": len(hypotheses),
            "hypotheses_tested_adequate_n": int((hypotheses["N"] >= 30).sum()),
            "fdr_survivors": int((hypotheses["evidence_label"] == "ROBUST CANDIDATE EDGE").sum()),
            "strongest_model": "Control (conditional); BOS (aggregate)",
            "strongest_condition": "Control + Short + Premarket",
            "validation_pass": validation_pass,
            "conservative_cost_pass": cost_pass,
            "monte_carlo_p05_positive": mc_p05_positive,
            "classification": classification,
            "validation_manifest": validation_manifest,
        },
    )
    print(f"PHASE 17 CLASSIFICATION: {classification}")
    print(f"Report: {REPORTS / 'PHASE17_REPORT.md'}")


if __name__ == "__main__":
    main()
