"""Analyze the one-time Phase 18 unseen run without changing frozen rules."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from phase16.indicators import score_band, session_bucket_name
from phase16.metrics import summarize_group


ROOT = Path(__file__).resolve().parents[1]
PHASE18 = ROOT / "phase18"
RESULTS = PHASE18 / "results"
BASE_RUN = RESULTS / "base_run"
FROZEN_PATH = ROOT / "phase17" / "results" / "frozen_candidates.json"
FROZEN_VALIDATION_MANIFEST = ROOT / "phase17" / "results" / "validation_manifest.json"
REFERENCE_SUMMARY = ROOT / "phase16" / "results" / "oos" / "model_comparison.csv"
REFERENCE_TRADES = ROOT / "phase16" / "results" / "oos" / "trades.csv"
BASELINE_SUMMARY = PHASE18 / "baseline_gate" / "model_comparison.csv"
BASELINE_TRADES = PHASE18 / "baseline_gate" / "trades.csv"

START = pd.Timestamp("2021-01-01", tz="America/Chicago")
END_EXCLUSIVE = pd.Timestamp("2023-12-29", tz="America/Chicago")
MODELS = ("Control", "BOS", "C1", "C2", "Retest", "Confirm")
NQ_DOLLARS_PER_POINT = 20.0
NQ_DOLLARS_PER_TICK = 5.0
MC_SIMULATIONS = 10_000

COST_SCENARIOS = {
    "Ideal/current": {"slippage_ticks_per_side": 0.0, "round_turn_commission_usd": 0.0},
    "Modest": {"slippage_ticks_per_side": 1.0, "round_turn_commission_usd": 4.50},
    "Standard conservative": {"slippage_ticks_per_side": 2.0, "round_turn_commission_usd": 8.00},
    "Severe": {"slippage_ticks_per_side": 3.0, "round_turn_commission_usd": 10.00},
    "Extreme": {"slippage_ticks_per_side": 4.0, "round_turn_commission_usd": 12.00},
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_trades(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in [item for item in frame.columns if item.endswith("timestamp")]:
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="coerce").dt.tz_convert(
            "America/Chicago"
        )
    return frame


def session_name(bucket: int) -> str:
    value = session_bucket_name(bucket)
    return {"Opening": "Open", "Morning": "MidAM", "Afternoon": "PM"}.get(value, value)


def decorate(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working["direction_name"] = working["direction"]
    working["session_name"] = working["session_bucket"].map(session_name)
    working["score_band"] = working["score"].map(score_band)
    working["stop_distance_points"] = (working["entry_price"] - working["stop_price"]).abs()
    return working


def apply_candidate(frame: pd.DataFrame, candidate: dict[str, object]) -> pd.DataFrame:
    group = frame.loc[frame["model"] == candidate["model"]].copy()
    for condition in candidate["conditions"]:
        group = group.loc[group[str(condition["feature"])] == condition["value"]]
    group["model"] = candidate["candidate_id"]
    return group


def drawdown_details(group: pd.DataFrame) -> tuple[float, int, float]:
    ordered = group.sort_values("exit_timestamp", kind="stable")
    if ordered.empty:
        return 0.0, 0, 0.0
    values = ordered["result_R"].astype(float).to_numpy()
    timestamps = ordered["exit_timestamp"].tolist()
    equity = np.cumsum(values)
    peak = 0.0
    peak_index = -1
    peak_time = START
    maximum_dd = 0.0
    maximum_trades = 0
    maximum_days = 0.0
    for index, (value, timestamp) in enumerate(zip(equity, timestamps)):
        if value >= peak:
            peak = float(value)
            peak_index = index
            peak_time = timestamp
        else:
            drawdown = peak - float(value)
            duration_trades = index - peak_index
            duration_days = (timestamp - peak_time).total_seconds() / 86400.0
            maximum_dd = max(maximum_dd, drawdown)
            maximum_trades = max(maximum_trades, duration_trades)
            maximum_days = max(maximum_days, duration_days)
    return maximum_dd, maximum_trades, maximum_days


def metrics(group: pd.DataFrame) -> dict[str, object]:
    ordered = group.sort_values("exit_timestamp", kind="stable")
    base = summarize_group(ordered)
    values = ordered["result_R"].astype(float).to_numpy() if len(ordered) else np.array([])
    n = len(values)
    standard_deviation = float(np.std(values, ddof=1)) if n >= 2 else float("nan")
    sem = standard_deviation / math.sqrt(n) if n >= 2 else float("nan")
    mean = float(np.mean(values)) if n else 0.0
    maximum_dd, dd_trades, dd_days = drawdown_details(ordered)
    base.update(
        {
            "flat": int(np.sum(values == 0)),
            "expectancy_R": mean,
            "std_trade_R": standard_deviation,
            "median_trade_R": float(np.median(values)) if n else 0.0,
            "sem_R": sem,
            "ci95_low_R": mean - 1.96 * sem if math.isfinite(sem) else float("nan"),
            "ci95_high_R": mean + 1.96 * sem if math.isfinite(sem) else float("nan"),
            "longest_drawdown_trades": dd_trades,
            "longest_drawdown_days": dd_days,
            "recovery_factor": float(base["total_R"]) / maximum_dd if maximum_dd > 0 else 0.0,
        }
    )
    return base


def calendar_results(model_frames: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    monthly_rows: list[dict[str, object]] = []
    quarterly_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    months = pd.period_range("2021-01", "2023-12", freq="M")
    quarters = pd.period_range("2021Q1", "2023Q4", freq="Q")
    years = (2021, 2022, 2023)
    for model, frame in model_frames.items():
        local = frame["entry_timestamp"].dt.tz_localize(None)
        month_period = local.dt.to_period("M")
        quarter_period = local.dt.to_period("Q")
        year_value = local.dt.year
        for period in months:
            monthly_rows.append(
                {"model": model, "month": str(period), **metrics(frame.loc[month_period == period])}
            )
        for period in quarters:
            quarterly_rows.append(
                {"model": model, "quarter": str(period), **metrics(frame.loc[quarter_period == period])}
            )
        for year in years:
            annual_rows.append(
                {"model": model, "year": year, **metrics(frame.loc[year_value == year])}
            )
    return pd.DataFrame(monthly_rows), pd.DataFrame(quarterly_rows), pd.DataFrame(annual_rows)


def model_comparison(
    model_frames: dict[str, pd.DataFrame],
    monthly: pd.DataFrame,
    quarterly: pd.DataFrame,
    annual: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for model in MODELS:
        summary = metrics(model_frames[model])
        months = monthly.loc[monthly["model"] == model]
        quarters = quarterly.loc[quarterly["model"] == model]
        years = annual.loc[annual["model"] == model]
        rows.append(
            {
                "model": model,
                **summary,
                "average_trades_per_month": summary["N"] / 36.0,
                "positive_months": int((months["total_R"] > 0).sum()),
                "total_months": 36,
                "positive_quarters": int((quarters["total_R"] > 0).sum()),
                "total_quarters": 12,
                "positive_years": int((years["total_R"] > 0).sum()),
                "total_years": 3,
            }
        )
    return pd.DataFrame(rows)


def cost_stress(candidate_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for candidate_id, frame in candidate_frames.items():
        risk_usd = frame["stop_distance_points"].astype(float) * NQ_DOLLARS_PER_POINT
        gross_total = float(frame["result_R"].sum())
        inverse_risk = float((1.0 / risk_usd).sum())
        break_even = gross_total / inverse_risk if inverse_risk > 0 else float("nan")
        for scenario, assumptions in COST_SCENARIOS.items():
            all_in = (
                assumptions["slippage_ticks_per_side"] * 2 * NQ_DOLLARS_PER_TICK
                + assumptions["round_turn_commission_usd"]
            )
            stressed = frame.copy()
            stressed["result_R"] = stressed["result_R"].astype(float) - all_in / risk_usd
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "scenario": scenario,
                    "slippage_ticks_per_side": assumptions["slippage_ticks_per_side"],
                    "round_turn_commission_usd": assumptions["round_turn_commission_usd"],
                    "all_in_cost_usd_per_trade": all_in,
                    "break_even_all_in_cost_usd_per_trade": break_even,
                    **metrics(stressed),
                }
            )
    return pd.DataFrame(rows)


def max_drawdown(values: Sequence[float]) -> float:
    array = np.asarray(values, dtype=float)
    if not len(array):
        return 0.0
    equity = np.cumsum(array)
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[1:]
    return float(np.max(peaks - equity, initial=0.0))


def longest_losing_streak(values: Sequence[float]) -> int:
    maximum = current = 0
    for value in values:
        current = current + 1 if float(value) < 0 else 0
        maximum = max(maximum, current)
    return maximum


def monte_carlo(candidate_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for number, (candidate_id, frame) in enumerate(candidate_frames.items(), start=1):
        values = frame.sort_values("exit_timestamp")["result_R"].astype(float).to_numpy()
        rng = np.random.default_rng(1800 + number)
        terminals = np.empty(MC_SIMULATIONS)
        drawdowns = np.empty(MC_SIMULATIONS)
        streaks = np.empty(MC_SIMULATIONS)
        for simulation in range(MC_SIMULATIONS):
            sample = rng.choice(values, size=len(values), replace=True)
            terminals[simulation] = sample.sum()
            drawdowns[simulation] = max_drawdown(sample)
            streaks[simulation] = longest_losing_streak(sample)
        rows.append(
            {
                "candidate_id": candidate_id,
                "simulations": MC_SIMULATIONS,
                "observed_N": len(values),
                "observed_total_R": float(values.sum()),
                "terminal_R_p05": float(np.quantile(terminals, 0.05)),
                "terminal_R_p25": float(np.quantile(terminals, 0.25)),
                "terminal_R_median": float(np.quantile(terminals, 0.50)),
                "terminal_R_p75": float(np.quantile(terminals, 0.75)),
                "terminal_R_p95": float(np.quantile(terminals, 0.95)),
                "probability_terminal_positive": float(np.mean(terminals > 0)),
                "max_DD_R_p05": float(np.quantile(drawdowns, 0.05)),
                "max_DD_R_p25": float(np.quantile(drawdowns, 0.25)),
                "max_DD_R_median": float(np.quantile(drawdowns, 0.50)),
                "max_DD_R_p75": float(np.quantile(drawdowns, 0.75)),
                "max_DD_R_p95": float(np.quantile(drawdowns, 0.95)),
                "probability_DD_over_10R": float(np.mean(drawdowns > 10)),
                "probability_DD_over_20R": float(np.mean(drawdowns > 20)),
                "probability_DD_over_30R": float(np.mean(drawdowns > 30)),
                "probability_DD_over_40R": float(np.mean(drawdowns > 40)),
                "probability_DD_over_50R": float(np.mean(drawdowns > 50)),
                "losing_streak_p05": float(np.quantile(streaks, 0.05)),
                "losing_streak_median": float(np.quantile(streaks, 0.50)),
                "losing_streak_p95": float(np.quantile(streaks, 0.95)),
            }
        )
    return pd.DataFrame(rows)


def outlier_stress(candidate_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for candidate_id, frame in candidate_frames.items():
        winners = frame.loc[frame["result_R"] > 0].sort_values("result_R", ascending=False)
        top_one_percent = max(1, math.ceil(len(winners) * 0.01)) if len(winners) else 0
        scenarios = {
            "Observed": [],
            "Exclude largest winning trade": winners.head(1).index.tolist(),
            "Exclude top 5 winning trades": winners.head(5).index.tolist(),
            "Exclude top 1% winning trades": winners.head(top_one_percent).index.tolist(),
        }
        for scenario, indexes in scenarios.items():
            stressed = frame.drop(index=indexes)
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "scenario": scenario,
                    "trades_removed": len(indexes),
                    **metrics(stressed),
                }
            )
    return pd.DataFrame(rows)


def pass_fail(
    comparison: pd.DataFrame,
    annual: pd.DataFrame,
    costs: pd.DataFrame,
    mc: pd.DataFrame,
    outliers: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    for candidate_id in ("C1", "C2"):
        summary = comparison.set_index("model").loc[candidate_id]
        years = annual.loc[annual["model"] == candidate_id]
        positive_year_totals = years.loc[years["total_R"] > 0, "total_R"]
        max_year_share = (
            float(positive_year_totals.max() / positive_year_totals.sum())
            if len(positive_year_totals) and positive_year_totals.sum() > 0
            else 1.0
        )
        conservative = costs.loc[
            (costs["candidate_id"] == candidate_id)
            & (costs["scenario"] == "Standard conservative")
        ].iloc[0]
        mc_row = mc.loc[mc["candidate_id"] == candidate_id].iloc[0]
        top_one = outliers.loc[
            (outliers["candidate_id"] == candidate_id)
            & (outliers["scenario"] == "Exclude top 1% winning trades")
        ].iloc[0]
        primary = {
            "total_R_positive": bool(summary["total_R"] > 0),
            "profit_factor_over_1_05": bool(summary["profit_factor"] > 1.05),
            "avg_R_positive": bool(summary["avg_R"] > 0),
            "at_least_200_trades": bool(summary["N"] >= 200),
            "at_least_half_years_positive": bool(summary["positive_years"] / summary["total_years"] >= 0.50),
            "no_year_over_60pct_positive_R": bool(max_year_share <= 0.60),
            "standard_conservative_total_R_positive": bool(conservative["total_R"] > 0),
        }
        primary_pass = all(primary.values())
        tail_threshold = -0.50 * float(summary["total_R"]) if summary["total_R"] > 0 else 0.0
        robust = {
            "MC_probability_at_least_90pct": bool(mc_row["probability_terminal_positive"] >= 0.90),
            "MC_p05_not_catastrophic": bool(mc_row["terminal_R_p05"] >= tail_threshold),
            "positive_after_removing_top_1pct_winners": bool(top_one["total_R"] > 0),
        }
        robust_pass = primary_pass and all(robust.values())
        classification = (
            "A — ROBUST OOS PASS"
            if robust_pass
            else "B — OOS PASS, FURTHER VALIDATION RECOMMENDED"
            if primary_pass
            else "D — OOS FAIL"
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                **primary,
                "positive_years": int(summary["positive_years"]),
                "total_years": int(summary["total_years"]),
                "largest_positive_year_share": max_year_share,
                "standard_conservative_total_R": float(conservative["total_R"]),
                "primary_pass": primary_pass,
                **robust,
                "MC_probability_terminal_positive": float(mc_row["probability_terminal_positive"]),
                "MC_terminal_R_p05": float(mc_row["terminal_R_p05"]),
                "MC_catastrophic_threshold_R": tail_threshold,
                "top_1pct_removed_total_R": float(top_one["total_R"]),
                "robust_pass": robust_pass,
                "classification": classification,
            }
        )
    return pd.DataFrame(rows)


def equity_paths(model_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for model, frame in model_frames.items():
        ordered = frame.sort_values("exit_timestamp", kind="stable").copy()
        ordered["cumulative_R"] = ordered["result_R"].cumsum()
        ordered["drawdown_R"] = ordered["cumulative_R"].cummax().clip(lower=0) - ordered["cumulative_R"]
        for row in ordered.itertuples():
            rows.append(
                {
                    "model": model,
                    "exit_timestamp": row.exit_timestamp,
                    "result_R": row.result_R,
                    "cumulative_R": row.cumulative_R,
                    "drawdown_R": row.drawdown_R,
                }
            )
    return pd.DataFrame(rows)


def plot_paths(paths: pd.DataFrame) -> None:
    plt.style.use("dark_background")
    colors = {
        "Control": "#9d9d9d",
        "BOS": "#d19a4b",
        "C1": "#23c9a5",
        "C2": "#5da7ff",
    }
    primary = ("Control", "BOS", "C1", "C2")
    fig, axis = plt.subplots(figsize=(12, 6))
    for model in primary:
        group = paths.loc[paths["model"] == model]
        axis.plot(group["exit_timestamp"], group["cumulative_R"], label=model, color=colors[model])
    axis.axhline(0, color="#777777", linewidth=1)
    axis.set_title("Phase 18 unseen OOS cumulative return")
    axis.set_xlabel("Exit timestamp (America/Chicago)")
    axis.set_ylabel("Cumulative R")
    axis.grid(alpha=0.18)
    axis.legend()
    fig.tight_layout()
    fig.savefig(PHASE18 / "equity_curve.png", dpi=160)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(12, 6))
    for model in primary:
        group = paths.loc[paths["model"] == model]
        axis.plot(group["exit_timestamp"], group["drawdown_R"], label=model, color=colors[model])
    axis.set_title("Phase 18 unseen OOS drawdown")
    axis.set_xlabel("Exit timestamp (America/Chicago)")
    axis.set_ylabel("Drawdown R")
    axis.grid(alpha=0.18)
    axis.legend()
    fig.tight_layout()
    fig.savefig(PHASE18 / "drawdown_curve.png", dpi=160)
    plt.close(fig)


def write_report(
    comparison: pd.DataFrame,
    annual: pd.DataFrame,
    costs: pd.DataFrame,
    mc: pd.DataFrame,
    outliers: pd.DataFrame,
    classifications: pd.DataFrame,
) -> None:
    indexed = comparison.set_index("model")
    classes = classifications.set_index("candidate_id")

    def metric_line(model: str) -> str:
        row = indexed.loc[model]
        return (
            f"N {int(row.N):,}; wins {int(row.wins):,}; losses {int(row.losses):,}; flat {int(row.flat):,}; "
            f"win rate {row.win_pct:.2f}%; Avg R {row.avg_R:.4f}; Total R {row.total_R:.2f}; "
            f"PF {row.profit_factor:.3f}; Max DD {row.max_drawdown_R:.2f}R"
        )

    annual_lines = []
    for model in ("Control", "BOS", "C1", "C2"):
        values = annual.loc[annual["model"] == model]
        annual_lines.append(
            f"- {model}: " + "; ".join(f"{int(row.year)} {row.total_R:.2f}R" for row in values.itertuples())
        )

    cost_lines = []
    for candidate_id in ("C1", "C2"):
        values = costs.loc[costs["candidate_id"] == candidate_id]
        cost_lines.append(
            f"- {candidate_id}: "
            + "; ".join(
                f"{row.scenario} {row.total_R:.2f}R/PF {row.profit_factor:.3f}"
                for row in values.itertuples()
            )
        )

    mc_lines = []
    for row in mc.itertuples():
        mc_lines.append(
            f"- {row.candidate_id}: median {row.terminal_R_median:.2f}R; p05 {row.terminal_R_p05:.2f}R; "
            f"p95 {row.terminal_R_p95:.2f}R; P(terminal > 0) {row.probability_terminal_positive:.1%}; "
            f"median Max DD {row.max_DD_R_median:.2f}R; p95 Max DD {row.max_DD_R_p95:.2f}R"
        )

    outlier_lines = []
    for candidate_id in ("C1", "C2"):
        values = outliers.loc[outliers["candidate_id"] == candidate_id]
        outlier_lines.append(
            f"- {candidate_id}: "
            + "; ".join(f"{row.scenario} {row.total_R:.2f}R" for row in values.itertuples())
        )

    c1 = indexed.loc["C1"]
    c2 = indexed.loc["C2"]
    control = indexed.loc["Control"]
    bos = indexed.loc["BOS"]
    phase_pass = bool(classifications["primary_pass"].any())
    overall = (
        "At least one predeclared conditional edge replicated on sacred unseen data."
        if phase_pass
        else "Neither predeclared Phase 17 conditional edge met the primary unseen-OOS gate."
    )

    report = f"""# Phase 18 — final unseen out-of-sample validation

## Scientific status

This was a one-time validation of the exact Phase 17 C1/C2 specifications. No Pine code, Phase 16 rule, Phase 17 candidate, threshold, filter, session, entry, stop, target, or scoring rule was changed. Phase 18 is now sacred observed data and may not be reused as OOS after any redesign.

## Data and baseline gates

- Baseline reproduction: **PASS** (exact model CSV, completed-trade CSV, and frozen-candidate SHA-256 matches).
- Databento: `GLBX.MDP3`, `ohlcv-1m`, continuous `NQ.v.0`.
- Cost estimate: **$3.9816**.
- Final unseen evaluation: **2021-01-01 through 2023-12-28 inclusive**, America/Chicago.
- OOS five-minute bars: **212,019**; raw one-minute rows: **1,090,620**.
- Data-validation gate: **PASS**; zero duplicate bars, zero invalid OHLC, zero adjusted roll gap, 13 provider rolls, zero development overlap.
- The preferred December 31 endpoint was shortened because the New Year closure supplied no bars to its end-exclusive boundary without entering 2024. See `data_validation.md`.

## Frozen model results

- Control: {metric_line('Control')}.
- BOS: {metric_line('BOS')}.
- C1 (Control + Short + Premarket): {metric_line('C1')}.
- C2 (BOS + Short + score 90–94): {metric_line('C2')}.
- Retest reference: {metric_line('Retest')}.
- Confirm reference: {metric_line('Confirm')}.

Full expectancy uncertainty, trade dispersion, drawdown duration, recovery factor, streaks, and time-count metrics are in `model_comparison.csv`.

## Annual stability

{chr(10).join(annual_lines)}

Monthly, quarterly, and annual tables include all calendar periods, including zero-trade periods, in their respective CSV files.

## Execution-cost stress

NQ conversion uses $20/point and $5/tick. The predeclared standard conservative case is two ticks per side plus $8.00 round-turn commission ($28/trade). Severe is three ticks per side plus $10 ($40/trade); extreme is four ticks per side plus $12 ($52/trade).

{chr(10).join(cost_lines)}

## Monte Carlo sequence risk

Ten thousand bootstrap trade-order resamples were run per candidate using the observed return distribution.

{chr(10).join(mc_lines)}

Drawdown exceedance probabilities for 10R, 20R, 30R, 40R, and 50R thresholds and losing-streak percentiles are in `monte_carlo_summary.csv`.

## Outlier dependence

{chr(10).join(outlier_lines)}

## Predeclared classifications

- C1: **{classes.loc['C1', 'classification']}**. Primary pass: {bool(classes.loc['C1', 'primary_pass'])}; robust pass: {bool(classes.loc['C1', 'robust_pass'])}.
- C2: **{classes.loc['C2', 'classification']}**. Primary pass: {bool(classes.loc['C2', 'primary_pass'])}; robust pass: {bool(classes.loc['C2', 'robust_pass'])}.

The numeric interpretation fixed before candidate metrics were evaluated defines “not catastrophically negative” as Monte Carlo terminal p05 >= −50% of observed positive Total R. Every individual criterion is recorded in `pass_fail.csv`.

## Required answers

1. **Did C1 replicate?** {'Yes under the primary gate.' if classes.loc['C1', 'primary_pass'] else 'No; it failed at least one primary criterion.'}
2. **Did C2 replicate?** {'Yes under the primary gate.' if classes.loc['C2', 'primary_pass'] else 'No; it failed at least one primary criterion.'}
3. **Did either outperform Control?** C1 {'did' if c1.avg_R > control.avg_R and c1.profit_factor > control.profit_factor else 'did not'} on Avg R and PF; C2 {'did' if c2.avg_R > control.avg_R and c2.profit_factor > control.profit_factor else 'did not'} on Avg R and PF.
4. **Did either outperform BOS?** C1 {'did' if c1.avg_R > bos.avg_R and c1.profit_factor > bos.profit_factor else 'did not'} on Avg R and PF; C2 {'did' if c2.avg_R > bos.avg_R and c2.profit_factor > bos.profit_factor else 'did not'} on Avg R and PF.
5. **Did the Phase 17 edge survive unseen data?** {overall}
6. **Did it survive realistic costs?** {'At least one candidate remained positive under the standard conservative scenario.' if (costs.loc[costs.scenario == 'Standard conservative', 'total_R'] > 0).any() else 'No candidate remained positive under the standard conservative scenario.'}
7. **Ready for paper/live forward testing?** {'Paper-only forward observation is reasonable for primary-pass candidates; live capital is not justified without operational forward evidence.' if phase_pass else 'No. The predeclared candidates should not advance to paper/live validation as claimed edges.'}

## Overall conclusion

{overall} Phase 18 results must be accepted without tuning. Any strategy change informed by this report creates a new development strategy requiring a different untouched dataset.
"""
    (PHASE18 / "PHASE18_OOS_REPORT.md").write_text(report)


def write_readme(classifications: pd.DataFrame) -> None:
    classes = classifications.set_index("candidate_id")
    text = f"""# Phase 18 — sacred unseen NQ validation

This directory permanently records the one-time 2021–2023 validation of the exact frozen Phase 17 C1/C2 candidates.

- C1: **{classes.loc['C1', 'classification']}**
- C2: **{classes.loc['C2', 'classification']}**
- Evaluation: 2021-01-01 through 2023-12-28 inclusive, America/Chicago
- Data: Databento `GLBX.MDP3` continuous `NQ.v.0`, 212,019 evaluated five-minute bars
- Cost estimate: $3.9816

Read `data_validation.md` before `PHASE18_OOS_REPORT.md`. Phase 18 data is now observed and may not be reused as unseen OOS after any strategy change.

Reproduction requires the already frozen Phase 16 environment and the exact hashes in `results/reproducibility_manifest.json`. The backtest command was:

```bash
phase16/.venv312/bin/python phase16/run_backtest.py \\
  --data phase18/data/processed/nq_5m.csv \\
  --start 2021-01-01 --end 2023-12-28 \\
  --mode oos --contracts prepared \\
  --parity-report phase16/results/parity/parity_summary.csv \\
  --debug-events --output phase18/results/base_run
```
"""
    (PHASE18 / "README.md").write_text(text)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    frozen = json.loads(FROZEN_PATH.read_text())
    validation_manifest = json.loads(FROZEN_VALIDATION_MANIFEST.read_text())
    candidate_hash = sha256(FROZEN_PATH)
    if candidate_hash != validation_manifest["frozen_candidates_sha256"]:
        raise RuntimeError("Frozen Phase 17 candidate hash mismatch")
    reference_summary = pd.read_csv(REFERENCE_SUMMARY)
    baseline_summary = pd.read_csv(BASELINE_SUMMARY)
    if not reference_summary.equals(baseline_summary):
        raise RuntimeError("Phase 16 baseline model summary mismatch")
    if sha256(REFERENCE_TRADES) != sha256(BASELINE_TRADES):
        raise RuntimeError("Phase 16 baseline completed-trade mismatch")

    base = decorate(read_trades(BASE_RUN / "trades.csv"))
    candidates = {candidate["candidate_id"]: apply_candidate(base, candidate) for candidate in frozen["candidates"]}
    if set(candidates) != {"C1", "C2"}:
        raise RuntimeError("Expected exact frozen candidates C1 and C2")
    model_frames = {
        "Control": base.loc[base["model"] == "Control"].copy(),
        "BOS": base.loc[base["model"] == "BOS"].copy(),
        "C1": candidates["C1"],
        "C2": candidates["C2"],
        "Retest": base.loc[base["model"] == "Retest"].copy(),
        "Confirm": base.loc[base["model"] == "Confirm"].copy(),
    }
    candidates["C1"].to_csv(PHASE18 / "trades_C1.csv", index=False)
    candidates["C2"].to_csv(PHASE18 / "trades_C2.csv", index=False)
    monthly, quarterly, annual = calendar_results(model_frames)
    monthly.to_csv(PHASE18 / "monthly_results.csv", index=False)
    quarterly.to_csv(PHASE18 / "quarterly_results.csv", index=False)
    annual.to_csv(PHASE18 / "annual_results.csv", index=False)
    comparison = model_comparison(model_frames, monthly, quarterly, annual)
    comparison.to_csv(PHASE18 / "model_comparison.csv", index=False)
    costs = cost_stress(candidates)
    costs.to_csv(PHASE18 / "cost_stress.csv", index=False)
    mc = monte_carlo(candidates)
    mc.to_csv(PHASE18 / "monte_carlo_summary.csv", index=False)
    outliers = outlier_stress(candidates)
    outliers.to_csv(PHASE18 / "outlier_stress.csv", index=False)
    classifications = pass_fail(comparison, annual, costs, mc, outliers)
    classifications.to_csv(PHASE18 / "pass_fail.csv", index=False)
    paths = equity_paths(model_frames)
    paths.to_csv(RESULTS / "equity_drawdown.csv", index=False)
    plot_paths(paths)
    manifest = {
        "dataset": "GLBX.MDP3",
        "schema": "ohlcv-1m",
        "symbol": "NQ.v.0",
        "raw_acquisition_start_utc": "2020-12-01T00:00:00Z",
        "raw_acquisition_end_exclusive_utc": "2024-01-01T06:00:00Z",
        "evaluation_start": str(START),
        "evaluation_end_exclusive": str(END_EXCLUSIVE),
        "databento_estimated_cost_usd": 3.9816,
        "raw_sha256": sha256(PHASE18 / "data" / "raw" / "nq_continuous_1m_raw.csv"),
        "processed_sha256": sha256(PHASE18 / "data" / "processed" / "nq_5m.csv"),
        "phase16_reference_summary_sha256": sha256(REFERENCE_SUMMARY),
        "phase16_reference_trades_sha256": sha256(REFERENCE_TRADES),
        "phase18_baseline_summary_sha256": sha256(BASELINE_SUMMARY),
        "phase18_baseline_trades_sha256": sha256(BASELINE_TRADES),
        "phase17_frozen_candidates_sha256": candidate_hash,
        "baseline_exact": True,
        "candidate_filtering_method": "Exact Phase 17 completed-trade subset conditions",
        "monte_carlo_simulations": MC_SIMULATIONS,
        "cost_scenarios": COST_SCENARIOS,
        "robust_tail_rule": "terminal_R_p05 >= -0.50 * observed positive Total R",
    }
    (RESULTS / "reproducibility_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write_report(comparison, annual, costs, mc, outliers, classifications)
    write_readme(classifications)
    print(comparison.loc[comparison["model"].isin(["Control", "BOS", "C1", "C2"])].to_string(index=False))
    print("\nCLASSIFICATIONS")
    print(classifications[["candidate_id", "primary_pass", "robust_pass", "classification"]].to_string(index=False))


if __name__ == "__main__":
    main()

