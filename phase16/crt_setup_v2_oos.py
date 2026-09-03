"""Preregistered one-shot OOS validation for frozen V2-B-LEGACY-EXP6."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import FrozenConfig
from .crt_setup_v2 import (
    SetupV2Archetype,
    SetupV2Qualification,
    SetupV2Variant,
    _excel_safe,
    run_setup_v2_backtest,
)
from .metrics import _drawdown
from .sequential_bos import (
    NQ_DOLLARS_PER_POINT,
    ROUND_TURN_COST_USD,
    apply_costs,
    summarize_architecture,
    verify_completed_trade_ordering,
)

FROZEN_VARIANT = SetupV2Variant(
    SetupV2Archetype.NEXT_BAR,
    SetupV2Qualification.LEGACY_QUALIFIED,
    6,
)
MC_SIMULATIONS = 10_000
CONTAMINATED_WINDOWS = [
    ("2024-01-01", "2026-06-26", "Phase 16/17/19 development + CRT_SETUP_V2"),
    ("2021-01-01", "2023-12-28", "Phase 18 one-time OOS (now sacred/observed)"),
    ("2021-01-01", "2023-12-29", "Phase 19 early baseline"),
    ("2021-01-01", "2026-06-26", "Phase 19 full scope + walk-forward"),
    ("2025-07-01", "2026-06-26", "Phase 17 sealed validation"),
    ("2024-01-01", "2025-06-30", "Phase 17 candidate discovery"),
    ("2026-06-29", "2026-08-18", "Pine-to-Python parity window"),
]


def _profit_factor(values: pd.Series) -> float:
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    if gross_loss > 0:
        return gross_profit / gross_loss
    return 99.9 if gross_profit > 0 else 0.0


def apply_cost_multiplier(trades: pd.DataFrame, multiplier: float) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    working = trades.copy()
    risk_points = (working.entry_price.astype(float) - working.stop_price.astype(float)).abs()
    cost_r = (ROUND_TURN_COST_USD * multiplier) / (risk_points * NQ_DOLLARS_PER_POINT)
    working["gross_R"] = working.result_R.astype(float)
    working["net_R"] = working.gross_R - cost_r
    return working


def summarize_net(trades: pd.DataFrame, *, cost_multiplier: float = 1.0) -> Dict[str, Any]:
    if trades.empty:
        return {
            "N": 0,
            "WR": 0.0,
            "net_AvgR": 0.0,
            "net_TotalR": 0.0,
            "net_PF": 0.0,
            "MaxDD": 0.0,
            "Long_N": 0,
            "Long_AvgR": 0.0,
            "Long_TotalR": 0.0,
            "Long_PF": 0.0,
            "Short_N": 0,
            "Short_AvgR": 0.0,
            "Short_TotalR": 0.0,
            "Short_PF": 0.0,
        }
    enriched = apply_cost_multiplier(trades.sort_values("exit_timestamp"), cost_multiplier)
    net = enriched.net_R.astype(float)
    summary = {
        "N": int(len(enriched)),
        "WR": float((net > 0).mean() * 100.0),
        "net_AvgR": float(net.mean()),
        "net_TotalR": float(net.sum()),
        "net_PF": _profit_factor(net),
        "MaxDD": _drawdown(net),
    }
    for direction in ("Long", "Short"):
        group = enriched.loc[enriched.direction == direction]
        if group.empty:
            summary[f"{direction}_N"] = 0
            summary[f"{direction}_AvgR"] = 0.0
            summary[f"{direction}_TotalR"] = 0.0
            summary[f"{direction}_PF"] = 0.0
        else:
            values = group.net_R.astype(float)
            summary[f"{direction}_N"] = int(len(group))
            summary[f"{direction}_AvgR"] = float(values.mean())
            summary[f"{direction}_TotalR"] = float(values.sum())
            summary[f"{direction}_PF"] = _profit_factor(values)
    return summary


def calendar_slices(trades: pd.DataFrame, config: FrozenConfig) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if trades.empty:
        empty = pd.DataFrame()
        return empty, empty, empty
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
    enriched = enriched.copy()
    enriched["year"] = entry_ts.dt.year
    enriched["quarter"] = entry_ts.dt.to_period("Q").astype(str)
    enriched["month"] = entry_ts.dt.to_period("M").astype(str)

    yearly = []
    for year, group in enriched.groupby("year"):
        yearly.append({"period": str(year), **summarize_net(group, cost_multiplier=1.0)})
    quarterly = []
    for quarter, group in enriched.groupby("quarter"):
        quarterly.append({"period": quarter, **summarize_net(group, cost_multiplier=1.0)})
    monthly = []
    for month, group in enriched.groupby("month"):
        monthly.append({"period": month, **summarize_net(group, cost_multiplier=1.0)})
    return pd.DataFrame(yearly), pd.DataFrame(quarterly), pd.DataFrame(monthly)


def time_stability_slices(trades: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    rows: List[Dict[str, Any]] = []
    split = len(enriched) // 2
    for label, group in (("first_half", enriched.iloc[:split]), ("second_half", enriched.iloc[split:])):
        rows.append({"slice": label, **summarize_net(group)})
    entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
    enriched = enriched.copy()
    enriched["month"] = entry_ts.dt.to_period("M")
    for month, group in enriched.groupby("month"):
        if len(group) < 3:
            continue
        window_end = month
        window_start = window_end - 5
        window = enriched.loc[(enriched["month"] >= window_start) & (enriched["month"] <= window_end)]
        if len(window) >= 10:
            rows.append(
                {
                    "slice": f"rolling_6m_{window_end}",
                    **summarize_net(window),
                }
            )
    return pd.DataFrame(rows)


def outlier_robustness(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    rows: List[Dict[str, Any]] = []
    scenarios = [
        ("full", enriched),
        ("exclude_best_trade", enriched.drop(enriched.net_R.idxmax())),
        ("exclude_top_3_winners", enriched.drop(enriched.nlargest(3, "net_R").index)),
        ("exclude_top_1pct_winners", enriched.loc[enriched.net_R <= enriched.net_R.quantile(0.99)]),
    ]
    for label, frame in scenarios:
        rows.append({"scenario": label, **summarize_net(frame)})
    return pd.DataFrame(rows)


def cost_stress(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for multiplier in (1.0, 1.5, 2.0):
        summary = summarize_net(trades, cost_multiplier=multiplier)
        rows.append(
            {
                "cost_multiplier": multiplier,
                "round_turn_usd": ROUND_TURN_COST_USD * multiplier,
                **summary,
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


def monte_carlo(trades: pd.DataFrame, *, seed: int = 2906) -> Dict[str, Any]:
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    values = enriched.net_R.astype(float).to_numpy()
    if len(values) == 0:
        return {"simulations": 0}
    rng = np.random.default_rng(seed)
    terminals = np.empty(MC_SIMULATIONS)
    drawdowns = np.empty(MC_SIMULATIONS)
    streaks = np.empty(MC_SIMULATIONS)
    for simulation in range(MC_SIMULATIONS):
        sample = rng.choice(values, size=len(values), replace=True)
        terminals[simulation] = sample.sum()
        drawdowns[simulation] = max_drawdown(sample)
        streaks[simulation] = longest_losing_streak(sample)
    return {
        "simulations": MC_SIMULATIONS,
        "observed_N": int(len(values)),
        "observed_total_R": float(values.sum()),
        "terminal_R_p05": float(np.quantile(terminals, 0.05)),
        "terminal_R_p25": float(np.quantile(terminals, 0.25)),
        "terminal_R_median": float(np.quantile(terminals, 0.50)),
        "terminal_R_p75": float(np.quantile(terminals, 0.75)),
        "terminal_R_p95": float(np.quantile(terminals, 0.95)),
        "probability_terminal_positive": float(np.mean(terminals > 0)),
        "max_DD_R_median": float(np.quantile(drawdowns, 0.50)),
        "max_DD_R_p95": float(np.quantile(drawdowns, 0.95)),
        "losing_streak_p05": float(np.quantile(streaks, 0.05)),
        "losing_streak_median": float(np.quantile(streaks, 0.50)),
        "losing_streak_p95": float(np.quantile(streaks, 0.95)),
    }


def evaluate_pass_criteria(
    trades: pd.DataFrame,
    *,
    yearly: pd.DataFrame,
    outlier: pd.DataFrame,
    cost: pd.DataFrame,
    mc: Dict[str, Any],
    first_half: Dict[str, Any],
    second_half: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
    full = summarize_net(trades)
    primary: List[Dict[str, Any]] = []
    strong: List[Dict[str, Any]] = []

    def add(rows: List[Dict[str, Any]], name: str, passed: bool, detail: str) -> None:
        rows.append({"criterion": name, "passed": passed, "detail": detail})

    add(primary, "N >= 100", full["N"] >= 100, f"N={full['N']}")
    add(primary, "Net AvgR > 0", full["net_AvgR"] > 0, f"AvgR={full['net_AvgR']:.4f}")
    add(primary, "Net PF > 1.05", full["net_PF"] > 1.05, f"PF={full['net_PF']:.4f}")
    add(primary, "Net TotalR > 0", full["net_TotalR"] > 0, f"TotalR={full['net_TotalR']:.2f}")
    dd_ok = full["net_TotalR"] <= 0 or full["MaxDD"] <= max(3.0 * full["net_TotalR"], 20.0)
    add(
        primary,
        "MaxDD not catastrophic vs TotalR",
        dd_ok,
        f"MaxDD={full['MaxDD']:.2f}, TotalR={full['net_TotalR']:.2f}",
    )
    if not yearly.empty:
        positive_years = int((yearly["net_TotalR"] > 0).sum())
        represented = len(yearly)
        year_ok = positive_years >= math.ceil(represented * 0.5)
        add(
            primary,
            ">=50% calendar years positive",
            year_ok,
            f"{positive_years}/{represented} years positive",
        )
    else:
        add(primary, ">=50% calendar years positive", False, "no yearly rows")
    if not outlier.empty:
        best = outlier.loc[outlier["scenario"] == "exclude_best_trade"].iloc[0]
        top1 = outlier.loc[outlier["scenario"] == "exclude_top_1pct_winners"].iloc[0]
        add(
            primary,
            "Positive excl. best trade",
            float(best["net_TotalR"]) > 0,
            f"TotalR={best['net_TotalR']:.2f}",
        )
        add(
            primary,
            "Positive excl. top 1% winners",
            float(top1["net_TotalR"]) > 0,
            f"TotalR={top1['net_TotalR']:.2f}",
        )
    else:
        add(primary, "Positive excl. best trade", False, "no trades")
        add(primary, "Positive excl. top 1% winners", False, "no trades")

    add(strong, "Net PF >= 1.15", full["net_PF"] >= 1.15, f"PF={full['net_PF']:.4f}")
    add(
        strong,
        "Positive first and second half",
        first_half.get("net_TotalR", 0) > 0 and second_half.get("net_TotalR", 0) > 0,
        f"first={first_half.get('net_TotalR', 0):.2f}, second={second_half.get('net_TotalR', 0):.2f}",
    )
    if not yearly.empty:
        positive_totals = yearly.loc[yearly["net_TotalR"] > 0, "net_TotalR"]
        if len(positive_totals) > 0 and float(positive_totals.sum()) > 0:
            max_share = float(positive_totals.max() / positive_totals.sum())
            add(strong, "No year >60% of positive TotalR", max_share <= 0.60, f"max_share={max_share:.2%}")
        else:
            add(strong, "No year >60% of positive TotalR", False, "no positive years")
    else:
        add(strong, "No year >60% of positive TotalR", False, "no yearly rows")
    if not cost.empty:
        stressed = cost.loc[cost["cost_multiplier"] == 1.5].iloc[0]
        add(
            strong,
            "Positive at 1.5x costs",
            float(stressed["net_TotalR"]) > 0,
            f"TotalR={stressed['net_TotalR']:.2f}",
        )
    else:
        add(strong, "Positive at 1.5x costs", False, "missing cost stress")
    add(
        strong,
        "MC P(terminal R > 0) >= 90%",
        float(mc.get("probability_terminal_positive", 0.0)) >= 0.90,
        f"P={mc.get('probability_terminal_positive', 0.0):.3f}",
    )

    primary_pass = all(row["passed"] for row in primary)
    strong_pass = all(row["passed"] for row in strong)
    if strong_pass:
        classification = "A — STRONG OOS PASS"
    elif primary_pass:
        classification = "B — OOS PASS"
    elif full["net_TotalR"] <= 0 or full["net_AvgR"] <= 0:
        classification = "D — OOS FAIL"
    else:
        classification = "C — MIXED / INCONCLUSIVE"
    return primary, strong, classification


def build_trade_trace(trades: pd.DataFrame, variant_id: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    enriched["variant_id"] = variant_id
    return enriched


def run_oos_validation(
    frame: pd.DataFrame,
    *,
    oos_start: str,
    oos_end: str,
    output: Path,
    config: FrozenConfig = FrozenConfig(),
    databento_cost_usd: float | None = None,
    acquisition_start: str | None = None,
    acquisition_end_exclusive: str | None = None,
    oos_bars: int | None = None,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    variant = FROZEN_VARIANT
    candidate_trades, counters, trace_rows, _ = run_setup_v2_backtest(
        frame,
        variant=variant,
        start=oos_start,
        end=oos_end,
        config=config,
    )
    frozen = run_backtest(frame, start=oos_start, end=oos_end, config=config)
    original_trades = frozen.trades.loc[frozen.trades.model == "Control"].copy()
    retest_trades = frozen.trades.loc[frozen.trades.model == "Confirm"].copy()

    from .sequential_bos import _prepare_data

    prepared = _prepare_data(frame, config)
    ordering_pass = True
    if counters.same_bar_bos_retest or counters.same_bar_retest_confirm:
        ordering_pass = False
    if not candidate_trades.empty:
        try:
            verify_completed_trade_ordering(candidate_trades, data_index=prepared.index)
        except AssertionError:
            ordering_pass = False

    full = summarize_net(candidate_trades)
    yearly, quarterly, monthly = calendar_slices(candidate_trades, config)
    outlier = outlier_robustness(candidate_trades)
    cost = cost_stress(candidate_trades)
    mc = monte_carlo(candidate_trades)
    stability = time_stability_slices(candidate_trades, config)
    if candidate_trades.empty:
        first_half = {}
        second_half = {}
    else:
        ordered = apply_costs(candidate_trades.sort_values("exit_timestamp"))
        split = len(ordered) // 2
        first_half = summarize_net(ordered.iloc[:split])
        second_half = summarize_net(ordered.iloc[split:])

    baselines = {
        "ORIGINAL": summarize_architecture(original_trades),
        "RETEST_GATED": summarize_architecture(retest_trades),
        "V2-B-LEGACY-EXP6": full,
    }
    primary, strong, classification = evaluate_pass_criteria(
        candidate_trades,
        yearly=yearly,
        outlier=outlier,
        cost=cost,
        mc=mc,
        first_half=first_half,
        second_half=second_half,
    )

    trace = build_trade_trace(candidate_trades, variant.variant_id)
    trace.to_csv(output / "oos_trade_trace.csv", index=False)
    pd.DataFrame([{"model": key, **value} for key, value in baselines.items()]).to_csv(
        output / "oos_summary.csv", index=False
    )
    yearly.to_csv(output / "oos_yearly.csv", index=False)
    quarterly.to_csv(output / "oos_quarterly.csv", index=False)
    monthly.to_csv(output / "oos_monthly.csv", index=False)
    cost.to_csv(output / "oos_cost_stress.csv", index=False)
    outlier.to_csv(output / "oos_outlier_robustness.csv", index=False)
    pd.DataFrame([mc]).to_csv(output / "oos_monte_carlo.csv", index=False)
    pd.DataFrame(primary).to_csv(output / "oos_primary_criteria.csv", index=False)
    pd.DataFrame(strong).to_csv(output / "oos_strong_criteria.csv", index=False)
    if not stability.empty:
        stability.to_csv(output / "oos_time_stability.csv", index=False)
    pd.DataFrame(trace_rows).to_csv(output / "oos_setup_trace.csv", index=False)

    manifest = {
        "frozen_candidate": variant.variant_id,
        "oos_start": oos_start,
        "oos_end": oos_end,
        "data_previously_unseen": True,
        "contaminated_windows": CONTAMINATED_WINDOWS,
        "databento": {
            "dataset": "GLBX.MDP3",
            "schema": "ohlcv-1m",
            "symbols": "NQ.v.0",
            "acquisition_start": acquisition_start,
            "acquisition_end_exclusive": acquisition_end_exclusive,
            "estimated_cost_usd": databento_cost_usd,
        },
        "oos_bars": oos_bars,
        "ordering_pass": ordering_pass,
        "same_bar_setup_bos_rejected": counters.same_bar_setup_bos,
        "result": full,
        "baselines": baselines,
        "primary_criteria": primary,
        "strong_criteria": strong,
        "classification": classification,
        "production_pine_recommendation": classification.startswith("A") or classification.startswith("B"),
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report = _build_report(manifest, yearly, quarterly, outlier, cost, mc, primary, strong)
    (output / "CRT_SETUP_V2_OOS_REPORT.md").write_text(report)

    with pd.ExcelWriter(output / "CRT_SETUP_V2_OOS.xlsx", engine="openpyxl") as writer:
        for name, df in (
            ("oos_summary", pd.DataFrame([{"model": k, **v} for k, v in baselines.items()])),
            ("oos_trade_trace", _excel_safe(trace)),
            ("oos_yearly", yearly),
            ("oos_quarterly", quarterly),
            ("oos_monthly", monthly),
            ("oos_cost_stress", cost),
            ("oos_outlier_robustness", outlier),
            ("oos_monte_carlo", pd.DataFrame([mc])),
            ("oos_primary_criteria", pd.DataFrame(primary)),
            ("oos_strong_criteria", pd.DataFrame(strong)),
        ):
            if not df.empty:
                _excel_safe(df).to_excel(writer, sheet_name=name[:31], index=False)

    return manifest


def _build_report(
    manifest: Dict[str, Any],
    yearly: pd.DataFrame,
    quarterly: pd.DataFrame,
    outlier: pd.DataFrame,
    cost: pd.DataFrame,
    mc: Dict[str, Any],
    primary: List[Dict[str, Any]],
    strong: List[Dict[str, Any]],
) -> str:
    result = manifest["result"]
    lines = [
        "# CRT Setup V2 Preregistered OOS Validation",
        "",
        f"**Frozen candidate:** `{manifest['frozen_candidate']}`",
        f"**OOS period:** {manifest['oos_start']} through {manifest['oos_end']} (America/Chicago)",
        f"**Data previously unseen:** YES",
        f"**Classification:** {manifest['classification']}",
        "",
        "## Contaminated development windows (not used as OOS)",
        "",
    ]
    for start, end, note in CONTAMINATED_WINDOWS:
        lines.append(f"- {start} → {end}: {note}")
    lines.extend(
        [
            "",
            "## Candidate OOS result",
            "",
            f"- N = {result['N']}",
            f"- WR = {result['WR']:.1f}%",
            f"- Net AvgR = {result['net_AvgR']:.4f}",
            f"- Net TotalR = {result['net_TotalR']:.2f}R",
            f"- Net PF = {result['net_PF']:.4f}",
            f"- MaxDD = {result['MaxDD']:.2f}R",
            "",
            "## Baselines (context only — not selection targets)",
            "",
        ]
    )
    for model, metrics in manifest["baselines"].items():
        if model == manifest["frozen_candidate"]:
            continue
        lines.append(
            f"- **{model}:** N={metrics['N']}, TotalR={metrics['net_TotalR']:.2f}R, PF={metrics['net_PF']:.3f}"
        )
    lines.extend(["", "## Primary criteria", ""])
    for row in primary:
        status = "PASS" if row["passed"] else "FAIL"
        lines.append(f"- [{status}] {row['criterion']}: {row['detail']}")
    lines.extend(["", "## Strong criteria", ""])
    for row in strong:
        status = "PASS" if row["passed"] else "FAIL"
        lines.append(f"- [{status}] {row['criterion']}: {row['detail']}")
    lines.extend(
        [
            "",
            "## Monte Carlo",
            "",
            f"- P(terminal R > 0) = {mc.get('probability_terminal_positive', 0.0):.3f}",
            f"- 5th percentile terminal R = {mc.get('terminal_R_p05', float('nan')):.2f}R",
            f"- Median terminal R = {mc.get('terminal_R_median', float('nan')):.2f}R",
            f"- 95th percentile terminal R = {mc.get('terminal_R_p95', float('nan')):.2f}R",
            f"- 95th percentile MaxDD = {mc.get('max_DD_R_p95', float('nan')):.2f}R",
            "",
            "## Production Pine recommendation",
            "",
            "YES" if manifest["production_pine_recommendation"] else "NO",
        ]
    )
    return "\n".join(lines) + "\n"
