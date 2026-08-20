"""File outputs and optional matplotlib charts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd

from .backtest import BacktestResult
from .config import FrozenConfig, write_frozen_config
from .metrics import (
    date_third_breakdowns,
    equity_path,
    model_summary,
    monthly_results,
    robustness_breakdowns,
)
from .validation import compare_breakdown_parity, compare_parity


def _write_diagnostics(path: Path, diagnostics: Dict[str, object], coverage: str) -> None:
    values = {key: str(value) for key, value in diagnostics.items()}
    values["Coverage"] = coverage
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n")


def plot_equity_drawdown(path: pd.DataFrame, output_directory: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for OOS charts; install requirements.txt"
        ) from exc
    output_directory.mkdir(parents=True, exist_ok=True)
    fig, axis = plt.subplots(figsize=(10, 5))
    if not path.empty:
        axis.plot(pd.to_datetime(path["exit_timestamp"]), path["cumulative_R"], color="#1261a0")
    axis.set_title("Frozen Retest — cumulative R")
    axis.set_xlabel("Exit time")
    axis.set_ylabel("R")
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_directory / "equity_curve.png", dpi=150)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(10, 5))
    if not path.empty:
        axis.fill_between(
            pd.to_datetime(path["exit_timestamp"]),
            path["drawdown_R"],
            color="#c0392b",
            alpha=0.55,
        )
    axis.set_title("Frozen Retest — drawdown")
    axis.set_xlabel("Exit time")
    axis.set_ylabel("Drawdown (R)")
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_directory / "drawdown_curve.png", dpi=150)
    plt.close(fig)


def write_common_outputs(
    result: BacktestResult,
    output_directory: str | Path,
    config: FrozenConfig,
    *,
    debug_events: bool,
) -> tuple[Path, pd.DataFrame]:
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    result.trades.to_csv(destination / "trades.csv", index=False)
    if debug_events:
        result.events.to_csv(destination / "event_debug.csv", index=False)
    summary = model_summary(result.trades)
    _write_diagnostics(destination / "diagnostics.json", result.diagnostics, result.coverage)
    write_frozen_config(destination / "frozen_config.json", config)
    return destination, summary


def write_parity_outputs(
    result: BacktestResult,
    output_directory: str | Path,
    config: FrozenConfig,
    *,
    reference: pd.DataFrame | None,
    breakdown_reference: pd.DataFrame | None = None,
    debug_events: bool,
) -> str:
    destination, summary = write_common_outputs(
        result, output_directory, config, debug_events=debug_events
    )
    if reference is None:
        summary = summary.copy()
        summary["parity_status"] = "REFERENCE REQUIRED"
        summary.to_csv(destination / "parity_summary.csv", index=False)
        return "REFERENCE REQUIRED"
    report, status = compare_parity(summary, reference)
    if breakdown_reference is not None:
        context = robustness_breakdowns(result.trades)
        thirds = date_third_breakdowns(
            result.trades, result.start_timestamp, result.end_exclusive
        )
        python_breakdowns = pd.concat([context, thirds], ignore_index=True)
        breakdown_report, breakdown_status = compare_breakdown_parity(
            python_breakdowns, breakdown_reference
        )
        breakdown_report.to_csv(destination / "breakdown_parity.csv", index=False)
        if breakdown_status != "PARITY PASS":
            status = "PARITY FAIL"
    if result.coverage != "FULL DATA":
        status = "PARITY FAIL"
        report["classification"] = "PARITY FAIL"
    report["overall_status"] = status
    report.to_csv(destination / "parity_summary.csv", index=False)
    summary.to_csv(destination / "python_summary.csv", index=False)
    return status


def write_oos_outputs(
    result: BacktestResult,
    output_directory: str | Path,
    config: FrozenConfig,
    *,
    debug_events: bool,
) -> None:
    destination, summary = write_common_outputs(
        result, output_directory, config, debug_events=debug_events
    )
    summary.to_csv(destination / "model_comparison.csv", index=False)
    retest_summary = summary.loc[summary["model"] == "Retest"]
    retest_summary.to_csv(destination / "oos_summary.csv", index=False)
    retest_trades = result.trades.loc[result.trades["model"] == "Retest"].copy()
    monthly_results(retest_trades).to_csv(destination / "monthly_results.csv", index=False)
    breakdowns = robustness_breakdowns(retest_trades)
    breakdowns.to_csv(destination / "breakdowns.csv", index=False)
    breakdowns.loc[breakdowns["dimension"] == "quarter"].to_csv(
        destination / "quarterly_results.csv", index=False
    )
    path = equity_path(retest_trades, "Retest")
    path.to_csv(destination / "equity_curve.csv", index=False)
    plot_equity_drawdown(path, destination)
