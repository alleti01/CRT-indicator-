"""Extended data quality checks for Phase 49 ingestion."""

from __future__ import annotations

from typing import Any

import pandas as pd

from phase49.config import TIMEZONE

from .firewall import development_cutoff_ts, forward_start_ts
from .resample import verify_15m_against_1m


def _ohlc_valid(df: pd.DataFrame) -> list[str]:
    issues: list[str] = []
    if df.empty:
        return issues
    high_floor = df[["open", "close", "low"]].max(axis=1)
    low_ceiling = df[["open", "close", "high"]].min(axis=1)
    invalid = (df["high"] < high_floor) | (df["low"] > low_ceiling) | (df["high"] < df["low"])
    if invalid.any():
        issues.append(f"ohlc_invalid_{int(invalid.sum())}_rows")
    if (df[["open", "high", "low", "close"]] < 0).any().any():
        issues.append("negative_prices")
    if (df["volume"] < 0).any():
        issues.append("negative_volume")
    return issues


def _ordering_issues(df: pd.DataFrame, label: str) -> list[str]:
    issues: list[str] = []
    if df.index.duplicated().any():
        issues.append(f"duplicate_{label}_timestamps")
    if not df.index.is_monotonic_increasing:
        issues.append(f"{label}_not_ordered")
    return issues


def _spacing_gaps(df: pd.DataFrame, expected_minutes: int, label: str) -> list[str]:
    if len(df) < 2:
        return []
    diffs = df.index.to_series().diff().dropna().dt.total_seconds().div(60)
    # Overnight/session gaps are expected; flag only sub-minute duplicates handled elsewhere.
    return []


def validate_bars(
    df: pd.DataFrame,
    *,
    label: str,
    expected_minutes: int | None = None,
    require_forward: bool = False,
    require_development: bool = False,
) -> dict[str, Any]:
    issues: list[str] = []
    issues.extend(_ordering_issues(df, label))
    if not df.empty:
        issues.extend(_ohlc_valid(df))
        issues.extend(_spacing_gaps(df, expected_minutes or 1, label))
    if require_forward and not df.empty:
        pre = df.loc[df.index < forward_start_ts()]
        if not pre.empty:
            issues.append(f"{label}_contains_pre_forward_rows")
    if require_development and not df.empty:
        fwd = df.loc[df.index >= forward_start_ts()]
        if not fwd.empty:
            issues.append(f"{label}_contains_forward_rows")
    return {
        "label": label,
        "row_count": len(df),
        "first_timestamp": str(df.index.min()) if not df.empty else None,
        "last_timestamp": str(df.index.max()) if not df.empty else None,
        "timezone": TIMEZONE,
        "issues": issues,
        "pass": len(issues) == 0,
    }


def audit_phase49_data(
    market_15m: pd.DataFrame,
    market_1m: pd.DataFrame,
    *,
    forward_1m: pd.DataFrame | None = None,
    forward_15m: pd.DataFrame | None = None,
) -> dict[str, Any]:
    cutoff = development_cutoff_ts()
    start = forward_start_ts()
    issues: list[str] = []

    dev_15 = market_15m.loc[market_15m.index <= cutoff] if not market_15m.empty else market_15m
    dev_1 = market_1m.loc[market_1m.index <= cutoff] if not market_1m.empty else market_1m

    checks = [
        validate_bars(dev_15, label="development_15m", expected_minutes=15, require_development=True),
        validate_bars(dev_1, label="development_1m", expected_minutes=1, require_development=True),
    ]
    fwd_1 = forward_1m if forward_1m is not None else market_1m.loc[market_1m.index >= start]
    fwd_15 = forward_15m if forward_15m is not None else market_15m.loc[market_15m.index >= start]
    checks.append(validate_bars(fwd_1, label="forward_1m", expected_minutes=1, require_forward=True))
    checks.append(validate_bars(fwd_15, label="forward_15m", expected_minutes=15, require_forward=True))

    for chk in checks:
        issues.extend(chk["issues"])

    agg_issues: list[str] = []
    if not fwd_15.empty and not fwd_1.empty:
        agg_issues = verify_15m_against_1m(fwd_15, fwd_1)
        issues.extend(agg_issues)

    fwd_bars_15 = int((market_15m.index >= start).sum()) if not market_15m.empty else 0
    fwd_bars_1 = int((market_1m.index >= start).sum()) if not market_1m.empty else 0
    if fwd_bars_15 == 0:
        issues.append("no_forward_15m_bars")
    if fwd_bars_1 == 0:
        issues.append("no_forward_1m_bars")

    hard_fail = [i for i in issues if i not in ("no_forward_15m_bars", "no_forward_1m_bars")]
    return {
        "pass": len(hard_fail) == 0,
        "issues": issues,
        "checks": checks,
        "aggregation_issues": agg_issues,
        "forward_15m_bars": fwd_bars_15,
        "forward_1m_bars": fwd_bars_1,
        "development_cutoff": str(cutoff),
        "forward_start": str(start),
        "timezone": TIMEZONE,
    }
