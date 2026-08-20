"""TradingView-versus-Python parity comparison and OOS gate."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import math

import pandas as pd


PARITY_METRICS = [
    "N",
    "wins",
    "losses",
    "win_pct",
    "avg_R",
    "total_R",
    "profit_factor",
    "max_drawdown_R",
]


def _normalize_reference(reference: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        "model": "model",
        "n": "N",
        "trades": "N",
        "wins": "wins",
        "losses": "losses",
        "win_%": "win_pct",
        "win_pct": "win_pct",
        "winrate": "win_pct",
        "avg_r": "avg_R",
        "total_r": "total_R",
        "pf": "profit_factor",
        "profit_factor": "profit_factor",
        "max_dd": "max_drawdown_R",
        "max_drawdown_r": "max_drawdown_R",
    }
    renamed = {}
    for column in reference.columns:
        key = str(column).strip().lower().replace(" ", "_")
        if key in aliases:
            renamed[column] = aliases[key]
    result = reference.rename(columns=renamed)
    if "model" not in result or "N" not in result or "total_R" not in result:
        raise ValueError("reference CSV must include model, N/trades, and total_R")
    return result


def classify_model(reference_n: float, python_n: float, reference_r: float, python_r: float) -> str:
    count_difference = abs(python_n - reference_n)
    r_difference = abs(python_r - reference_r)
    pass_r = max(0.50, abs(reference_r) * 0.10)
    warning_r = max(1.50, abs(reference_r) * 0.25)
    if count_difference <= 2 and r_difference <= pass_r:
        return "PARITY PASS"
    if count_difference <= 5 and r_difference <= warning_r:
        return "PARITY WARNING"
    return "PARITY FAIL"


def compare_parity(
    python_summary: pd.DataFrame, reference: pd.DataFrame
) -> Tuple[pd.DataFrame, str]:
    """Compare against a user-supplied TV export; no target is embedded here."""
    tv = _normalize_reference(reference)
    merged = tv.merge(python_summary, on="model", how="outer", suffixes=("_tv", "_python"))
    classifications: Dict[str, str] = {}
    for row in merged.itertuples():
        if pd.isna(getattr(row, "N_tv", float("nan"))) or pd.isna(
            getattr(row, "N_python", float("nan"))
        ):
            classifications[str(row.model)] = "PARITY FAIL"
        else:
            classifications[str(row.model)] = classify_model(
                float(row.N_tv),
                float(row.N_python),
                float(row.total_R_tv),
                float(row.total_R_python),
            )
    rows = []
    for row in merged.itertuples(index=False):
        values = row._asdict()
        model = str(values["model"])
        for metric in PARITY_METRICS:
            tv_value = values.get(f"{metric}_tv")
            py_value = values.get(f"{metric}_python")
            if tv_value is None or py_value is None or pd.isna(tv_value) or pd.isna(py_value):
                continue
            absolute = abs(float(py_value) - float(tv_value))
            percentage = absolute * 100.0 / abs(float(tv_value)) if float(tv_value) != 0 else float("nan")
            rows.append(
                {
                    "model": model,
                    "metric": metric,
                    "tradingview": float(tv_value),
                    "python": float(py_value),
                    "absolute_difference": absolute,
                    "percentage_difference": percentage,
                    "classification": classifications[model],
                }
            )
    report = pd.DataFrame(rows)
    statuses = set(classifications.values())
    overall = (
        "PARITY FAIL"
        if "PARITY FAIL" in statuses
        else "PARITY WARNING"
        if "PARITY WARNING" in statuses
        else "PARITY PASS"
    )
    report["overall_status"] = overall
    return report, overall


def read_reference(path: str | Path) -> pd.DataFrame:
    return _normalize_reference(pd.read_csv(path))


def require_parity_pass(path: str | Path) -> None:
    report = pd.read_csv(path)
    if "overall_status" not in report.columns or report.empty:
        raise RuntimeError("OOS is blocked: parity report has no overall_status")
    statuses = set(report["overall_status"].dropna().astype(str))
    if statuses != {"PARITY PASS"}:
        status = ", ".join(sorted(statuses)) or "UNKNOWN"
        raise RuntimeError(f"OOS is blocked until parity passes (current: {status})")


def _pine_display_round(value: float, decimals: int) -> float:
    scale = 10**decimals
    scaled = float(value) * scale
    rounded = math.floor(scaled + 0.5) if scaled >= 0 else math.ceil(scaled - 0.5)
    return rounded / scale


def compare_breakdown_parity(
    python_breakdowns: pd.DataFrame, reference: pd.DataFrame
) -> Tuple[pd.DataFrame, str]:
    """Compare all screenshot rows at Pine's displayed precision."""
    keys = ["model", "dimension", "bucket"]
    metrics = {
        "N": 0,
        "win_pct": 0,
        "avg_R": 2,
        "total_R": 2,
        "profit_factor": 1,
    }
    required = set(keys) | set(metrics)
    if not required.issubset(reference.columns):
        missing = sorted(required - set(reference.columns))
        raise ValueError(f"breakdown reference is missing: {missing}")
    merged = reference.merge(
        python_breakdowns, on=keys, how="left", suffixes=("_tv", "_python")
    )
    rows = []
    overall = "PARITY PASS"
    for source in merged.to_dict("records"):
        row = {key: source[key] for key in keys}
        mismatches = []
        for metric, decimals in metrics.items():
            tv = float(source[f"{metric}_tv"])
            raw_python = source.get(f"{metric}_python")
            py = 0.0 if pd.isna(raw_python) else float(raw_python)
            displayed_python = _pine_display_round(py, decimals)
            matches = displayed_python == tv
            if not matches:
                mismatches.append(metric)
            row[f"{metric}_tradingview"] = tv
            row[f"{metric}_python_displayed"] = displayed_python
        row["status"] = "PASS" if not mismatches else "FAIL"
        row["mismatches"] = ",".join(mismatches)
        if mismatches:
            overall = "PARITY FAIL"
        rows.append(row)
    report = pd.DataFrame(rows)
    report["overall_status"] = overall
    return report, overall
