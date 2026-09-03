"""Data provenance gate — HARD GATE before any performance research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from phase57d.config import REQUIRED_OPTIONS_FIELDS, RESULTS
from phase57d.research.inventory import inventory_datasets
from phase57d.research.schema import DATA_PROVENANCE_COLUMNS


PROVENANCE_QUESTIONS = {
    "oi_intraday_or_prior_clearing": "UNKNOWN — no options data present",
    "oi_known_time": "UNKNOWN — no options data present",
    "greeks_historical_snapshots": "UNKNOWN — no options data present",
    "greeks_recompute_inputs": "UNKNOWN — no options data present",
    "iv_point_in_time": "UNKNOWN — no options data present",
    "volume_cumulative_intraday": "UNKNOWN — no options data present",
    "expired_contracts_preserved": "UNKNOWN — no options data present",
    "all_strikes_preserved": "UNKNOWN — no options data present",
    "survivorship_bias": "UNKNOWN — no options data present",
    "timestamp_exchange_or_vendor": "UNKNOWN — no options data present",
    "known_latency": "UNKNOWN — no options data present",
    "wall_before_touch_provable": "NO — no options data to prove",
}


def _nq_underlying_row() -> dict[str, Any]:
    inv = inventory_datasets()
    ds = inv["underlying_datasets"]
    first = ds[0] if ds else {}
    return {
        "dataset": first.get("dataset", "nq_continuous_1m (multiple paths)"),
        "provider": "project_internal",
        "underlying": "NQ",
        "options_product": "N/A",
        "start_date": "2017-10-01 (approx, stitched)",
        "end_date": "2026-06-26 (approx, stitched)",
        "snapshot_frequency": "1M closed bars",
        "timestamp_timezone": "America/Chicago",
        "OI_frequency": "NOT_APPLICABLE",
        "OI_known_time": "NOT_APPLICABLE",
        "IV_source": "NOT_APPLICABLE",
        "Greeks_source": "NOT_APPLICABLE",
        "volume_type": "futures_volume",
        "historical_revision_status": "static_csv",
        "point_in_time_verified": "YES (OHLC closed bars)",
        "known_latency": "0 (closed bar)",
        "limitations": "Underlying only; no options chain",
    }


def build_provenance_table() -> pd.DataFrame:
    """Build data_provenance.csv content."""
    rows = [_nq_underlying_row()]

    inv = inventory_datasets()
    for opt in inv["options_datasets"]:
        rows.append({
            "dataset": opt.get("dataset", ""),
            "provider": "unknown",
            "underlying": "unknown",
            "options_product": "unknown",
            "start_date": "",
            "end_date": "",
            "snapshot_frequency": "",
            "timestamp_timezone": "",
            "OI_frequency": "UNKNOWN",
            "OI_known_time": "UNKNOWN",
            "IV_source": "UNKNOWN",
            "Greeks_source": "UNKNOWN",
            "volume_type": "UNKNOWN",
            "historical_revision_status": "UNKNOWN",
            "point_in_time_verified": "NO",
            "known_latency": "UNKNOWN",
            "limitations": "Candidate file; not validated as point-in-time options",
        })

    if not inv["options_datasets"]:
        for mapping, product in [
            ("MAP_NQ_NQOPT", "NQ futures options"),
            ("MAP_NQ_NDX", "NDX index options"),
            ("MAP_NQ_QQQ", "QQQ ETF options"),
        ]:
            rows.append({
                "dataset": f"MISSING:{mapping}",
                "provider": "NOT_AVAILABLE",
                "underlying": "NQ",
                "options_product": product,
                "start_date": "",
                "end_date": "",
                "snapshot_frequency": "",
                "timestamp_timezone": "",
                "OI_frequency": "NOT_AVAILABLE",
                "OI_known_time": "NOT_AVAILABLE",
                "IV_source": "NOT_AVAILABLE",
                "Greeks_source": "NOT_AVAILABLE",
                "volume_type": "NOT_AVAILABLE",
                "historical_revision_status": "NOT_AVAILABLE",
                "point_in_time_verified": "NO",
                "known_latency": "NOT_AVAILABLE",
                "limitations": (
                    f"No historical point-in-time {product} data in repository. "
                    f"Required fields: {', '.join(REQUIRED_OPTIONS_FIELDS)}"
                ),
            })

    return pd.DataFrame(rows, columns=DATA_PROVENANCE_COLUMNS)


def evaluate_provenance_gate() -> dict[str, Any]:
    """Evaluate whether point-in-time options research can proceed."""
    inv = inventory_datasets()
    table = build_provenance_table()

    options_verified = table[
        (table["options_product"] != "N/A")
        & (table["point_in_time_verified"] == "YES")
    ]

    gate_pass = len(options_verified) > 0 and inv["has_point_in_time_options"]

    return {
        "gate_pass": gate_pass,
        "status": "PASS" if gate_pass else "FAIL",
        "overall": "INVALID_DATA" if not gate_pass else "VALID",
        "underlying_available": inv["underlying_count"] > 0,
        "options_available": inv["options_count"] > 0,
        "options_point_in_time_verified": len(options_verified) > 0,
        "performance_research_permitted": gate_pass,
        "wall_edge_claims_permitted": gate_pass,
        "questions": PROVENANCE_QUESTIONS,
        "required_fields": list(REQUIRED_OPTIONS_FIELDS),
        "missing_mappings": ["MAP_NQ_NQOPT", "MAP_NQ_NDX", "MAP_NQ_QQQ"],
        "reconstructable_wall_families": {
            "CALL_WALL": "BLOCKED — needs OI or gamma snapshots",
            "PUT_WALL": "BLOCKED — needs OI or gamma snapshots",
            "GAMMA_WALL": "BLOCKED — needs Greeks + sign assumption",
            "IV_WALL": "BLOCKED — needs IV surface snapshots",
            "OI_WALL": "BLOCKED — needs OI with known timing",
            "ZERO_GAMMA": "BLOCKED — needs gamma exposure methodology + data",
            "MULTI_EXP": "BLOCKED — needs multi-expiration snapshots",
        },
    }


def save_provenance() -> tuple[Path, dict]:
    """Write data_provenance.csv and return gate evaluation."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    table = build_provenance_table()
    csv_path = RESULTS / "data_provenance.csv"
    table.to_csv(csv_path, index=False)
    gate = evaluate_provenance_gate()
    return csv_path, gate
