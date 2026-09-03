"""Dataset inventory — scan repository for available data sources."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase57d.config import DATA, PHASE57D_ROOT, REQUIRED_OPTIONS_FIELDS, ROOT, TIMEZONE


def _scan_nq_futures() -> list[dict]:
    """Inventory NQ futures OHLC datasets."""
    patterns = [
        "**/nq_continuous_1m*.csv",
        "**/nq_continuous_5m*.csv",
        "**/nq_continuous_15m*.csv",
    ]
    found: dict[str, dict] = {}
    for pat in patterns:
        for p in ROOT.glob(pat):
            if "phase57d" in str(p):
                continue
            key = str(p.relative_to(ROOT))
            if key in found:
                continue
            try:
                df = pd.read_csv(p, nrows=3)
                cols = list(df.columns)
            except Exception:
                cols = []
            found[key] = {
                "dataset": key,
                "type": "underlying_ohlc",
                "provider": "project_internal",
                "underlying": "NQ",
                "format": "csv",
                "columns": cols,
                "path": str(p),
            }
    return list(found.values())


def _scan_options() -> list[dict]:
    """Search for verified options chain datasets (strict filename match)."""
    keywords = ("option", "options_chain", "gex", "open_interest", "oi_chain", "iv_surface")
    found: list[dict] = []
    seen: set[str] = set()
    for p in ROOT.rglob("*"):
        if "phase57d" in str(p) or not p.is_file():
            continue
        if p.suffix not in (".csv", ".parquet", ".feather", ".json"):
            continue
        name_lower = p.name.lower()
        if not any(kw in name_lower for kw in keywords):
            continue
        rel = str(p.relative_to(ROOT))
        if rel in seen:
            continue
        seen.add(rel)
        found.append({
            "dataset": rel,
            "type": "candidate_options",
            "path": str(p),
            "suffix": p.suffix,
            "verified": False,
        })
    return found


def inventory_datasets() -> dict:
    """Full repository data inventory."""
    nq = _scan_nq_futures()
    options = _scan_options()
    return {
        "scan_root": str(ROOT),
        "timezone": TIMEZONE,
        "underlying_datasets": nq,
        "options_datasets": options,
        "options_count": len(options),
        "underlying_count": len(nq),
        "required_options_fields": list(REQUIRED_OPTIONS_FIELDS),
        "has_point_in_time_options": False,
    }


def save_inventory(path: Path | None = None) -> Path:
    path = path or (DATA / "dataset_inventory.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    inv = inventory_datasets()
    path.write_text(json.dumps(inv, indent=2))
    return path
