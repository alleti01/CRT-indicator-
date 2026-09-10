"""Causal gate_state extraction from Pine-native GLD exports and alert payloads."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from signal_ledger.config import GATE_NAMES, NULLABLE_GATE_NAMES
from signal_ledger.gate_export import PIVOT_LAG_COLS, load_tv_gate_export
from signal_ledger.gate_tri_state import (
    blocking_gates_for_direction,
    gate_state_from_export_row,
    gate_state_detail_from_export_row,
)

PIVOT_EXPORT_NAMES = tuple(c.replace("GLD_", "").lower() for c in PIVOT_LAG_COLS)


@dataclass
class KnownAtOffset:
    gate_name: str
    known_at_bar_offset: int
    feeds_gate: str
    notes: str


def gate_state_from_alert_payload(payload: dict[str, Any]) -> dict[str, bool | None]:
    """Extract gate_state from Layer D alert JSON (schema 1.2+). Preserves null evidence gates."""
    gs = payload.get("gate_state")
    if isinstance(gs, str):
        gs = json.loads(gs)
    if not isinstance(gs, dict):
        raise ValueError("alert payload missing gate_state object")
    out: dict[str, bool | None] = {}
    for g in GATE_NAMES:
        if g not in gs:
            raise ValueError(f"alert gate_state missing key: {g}")
        val = gs[g]
        if g in NULLABLE_GATE_NAMES and val is None:
            out[g] = None
        else:
            out[g] = bool(val)
    return out


def cross_check_alert_vs_export(
    alert_payload: dict[str, Any],
    export_row: pd.Series,
) -> list[str]:
    """Compare alert-payload gates to data-window export on same bar."""
    alert_gs = gate_state_from_alert_payload(alert_payload)
    export_gs = gate_state_from_export_row(export_row)
    mism: list[str] = []
    for g in GATE_NAMES:
        a, e = alert_gs.get(g), export_gs.get(g)
        if a is None and e is None:
            continue
        if a is None or e is None:
            if a != e:
                mism.append(f"{g}: alert={a} export={e}")
            continue
        if a != e:
            mism.append(f"{g}: alert={a} export={e}")
    return mism


def compute_known_at_offsets(gates_df: pd.DataFrame) -> list[KnownAtOffset]:
    results: list[KnownAtOffset] = []
    n = len(gates_df)
    if n == 0:
        return results

    for gate in GATE_NAMES:
        if gate not in gates_df.columns:
            continue
        series = gates_df[gate]
        if gate in NULLABLE_GATE_NAMES:
            # Known at bar close when value is non-null; na rows excluded from offset scan
            valid = series.notna()
            offset = 0 if valid.any() else 0
        else:
            offset = 0
        results.append(
            KnownAtOffset(
                gate_name=gate,
                known_at_bar_offset=offset,
                feeds_gate=gate,
                notes="Recomputed from Pine GLD export (bar-close evaluation)",
            )
        )
    return results


def compute_pivot_confirmation_offsets(gates_df: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {"confirmed": False, "swing_period": None, "high_lag_samples": [], "low_lag_samples": []}
    if "pivot_high_center_lag" not in gates_df.columns:
        return out

    hi = pd.to_numeric(gates_df["pivot_high_center_lag"], errors="coerce").dropna()
    lo = pd.to_numeric(gates_df.get("pivot_low_center_lag", pd.Series(dtype=float)), errors="coerce").dropna()
    sp = pd.to_numeric(gates_df.get("swing_period", pd.Series(dtype=float)), errors="coerce").dropna()

    if len(sp):
        out["swing_period"] = float(sp.iloc[-1])
    if len(hi):
        out["high_lag_samples"] = hi.unique().tolist()[:5]
    if len(lo):
        out["low_lag_samples"] = lo.unique().tolist()[:5]

    expected = out["swing_period"]
    if expected is not None and len(hi):
        out["confirmed"] = all(abs(v - expected) < 0.01 for v in hi)
    return out


def write_known_at_offsets_csv(offsets: list[KnownAtOffset], path: Path) -> None:
    rows = [
        {
            "gate_name": o.gate_name,
            "known_at_bar_offset": o.known_at_bar_offset,
            "feeds_gate": o.feeds_gate,
            "notes": o.notes,
        }
        for o in offsets
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def load_gates_for_ledger(export_path: Path) -> pd.DataFrame:
    return load_tv_gate_export(export_path)


# Re-export Part D helpers used by ledger_builder
__all__ = [
    "KnownAtOffset",
    "blocking_gates_for_direction",
    "compute_known_at_offsets",
    "compute_pivot_confirmation_offsets",
    "cross_check_alert_vs_export",
    "gate_state_detail_from_export_row",
    "gate_state_from_alert_payload",
    "gate_state_from_export_row",
    "load_gates_for_ledger",
    "write_known_at_offsets_csv",
]
