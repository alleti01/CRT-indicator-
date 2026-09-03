"""Research registry — append-only log of every configuration tested."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from phase57.config import RESULTS


REGISTRY_PATH = RESULTS / "research_registry.csv"

FIELDS = [
    "config_id",
    "timestamp",
    "family",
    "hypothesis",
    "parameters",
    "train_N",
    "train_AvgR",
    "train_PF",
    "oos_N",
    "oos_AvgR",
    "oos_PF",
    "oos_TotalR",
    "oos_MaxDD",
    "year_stability",
    "frequency_per_day",
    "entry_latency_bars",
    "retention_pct",
    "status",
    "reason",
]


def _ensure_header() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_PATH.exists():
        with REGISTRY_PATH.open("w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def register(
    family: str,
    hypothesis: str,
    parameters: str,
    *,
    train_metrics: dict | None = None,
    oos_metrics: dict | None = None,
    year_stability: str = "",
    frequency_per_day: float | None = None,
    entry_latency_bars: float | None = None,
    retention_pct: float | None = None,
    status: str = "TESTED",
    reason: str = "",
) -> str:
    _ensure_header()
    config_id = f"P57-{uuid.uuid4().hex[:8]}"
    tm = train_metrics or {}
    om = oos_metrics or {}
    row = {
        "config_id": config_id,
        "timestamp": datetime.now().isoformat(),
        "family": family,
        "hypothesis": hypothesis,
        "parameters": parameters,
        "train_N": tm.get("N", ""),
        "train_AvgR": tm.get("AvgR", ""),
        "train_PF": tm.get("PF", ""),
        "oos_N": om.get("N", ""),
        "oos_AvgR": om.get("AvgR", ""),
        "oos_PF": om.get("PF", ""),
        "oos_TotalR": om.get("TotalR", ""),
        "oos_MaxDD": om.get("MaxDD", ""),
        "year_stability": year_stability,
        "frequency_per_day": frequency_per_day if frequency_per_day is not None else "",
        "entry_latency_bars": entry_latency_bars if entry_latency_bars is not None else "",
        "retention_pct": retention_pct if retention_pct is not None else "",
        "status": status,
        "reason": reason,
    }
    with REGISTRY_PATH.open("a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow(row)
    return config_id


def read_registry() -> pd.DataFrame:
    _ensure_header()
    return pd.read_csv(REGISTRY_PATH)


def total_configs_tested() -> int:
    return len(read_registry())
