"""Part D — three-state interpretation for GLD export rows (no silent NaN→False)."""
from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from signal_ledger.config import (
    ARM_TOTAL_PROV_COLD_START,
    ARM_TOTAL_PROV_FRESH,
    ARM_TOTAL_PROV_STALE_HOLD,
    GATE_NAMES,
    NULLABLE_GATE_NAMES,
    PASS_REASON_INSUFFICIENT_WARMUP,
)

ArmTotalState = Literal["insufficient_warmup", "fresh", "stale_hold", "unset"]
EvidenceState = Literal["pass", "fail", "insufficient_warmup", "unknown_na"]


def _is_na(val: Any) -> bool:
    if val is None:
        return True
    try:
        return bool(pd.isna(val))
    except (TypeError, ValueError):
        return False


def arm_total_state(row: pd.Series, side: str) -> ArmTotalState:
    """Interpret GLD_arm_total_{side}_prov + value."""
    prov_col = f"arm_total_{side}_prov"
    val_col = f"arm_total_{side}"
    if prov_col not in row.index:
        # Legacy export without prov columns — treat numeric value as fresh if present
        if _is_na(row.get(val_col)):
            return "unset"
        return "fresh"
    prov = row.get(prov_col)
    if _is_na(prov):
        return "unset"
    p = int(prov)
    if p == ARM_TOTAL_PROV_COLD_START:
        # prov=0 overloads cold-start vs warm unset snap — disambiguate with Part C markers
        pass_reason = row.get("pass_reason_code", 0)
        warmup = row.get("htf_warmup_ready")
        if not _is_na(pass_reason) and int(pass_reason) == PASS_REASON_INSUFFICIENT_WARMUP:
            return "insufficient_warmup"
        if not _is_na(warmup) and not bool(warmup):
            return "insufficient_warmup"
        return "unset"
    if p == ARM_TOTAL_PROV_FRESH:
        return "fresh"
    if p == ARM_TOTAL_PROV_STALE_HOLD:
        return "stale_hold"
    return "unset"


def evidence_threshold_state(row: pd.Series, side: str) -> EvidenceState:
    """
    Interpret evidence_threshold gate without coercing export na to fail.

    - pass / fail: warm export with explicit true/false
    - insufficient_warmup: pass_reason_code or cold arm-total prov
    - unknown_na: na export without cold-start markers
    """
    gate = f"evidence_threshold_{side}"
    raw = row.get(gate) if gate in row.index else None
    pass_reason = row.get("pass_reason_code", 0)
    arm = arm_total_state(row, side)

    if not _is_na(pass_reason) and int(pass_reason) == PASS_REASON_INSUFFICIENT_WARMUP:
        return "insufficient_warmup"
    if arm == "insufficient_warmup":
        return "insufficient_warmup"
    if _is_na(raw):
        warmup = row.get("htf_warmup_ready")
        if not _is_na(warmup) and not bool(warmup):
            return "insufficient_warmup"
        return "unknown_na"
    return "pass" if bool(raw) else "fail"


def gate_state_from_export_row(row: pd.Series) -> dict[str, bool | None]:
    """
    Gate booleans for ledger JSON. Nullable gates preserve None (export na / cold-start).
    """
    out: dict[str, bool | None] = {}
    for g in GATE_NAMES:
        if g not in row.index:
            continue
        val = row[g]
        if g in NULLABLE_GATE_NAMES and _is_na(val):
            out[g] = None
        else:
            out[g] = bool(val)
    return out


def gate_state_detail_from_export_row(row: pd.Series) -> dict[str, Any]:
    """Extended gate metadata for ledger rows (Part D three-state)."""
    detail: dict[str, Any] = {
        "evidence_threshold_long_state": evidence_threshold_state(row, "long"),
        "evidence_threshold_short_state": evidence_threshold_state(row, "short"),
        "arm_total_long_state": arm_total_state(row, "long"),
        "arm_total_short_state": arm_total_state(row, "short"),
    }
    for col in ("arm_total_long", "arm_total_short", "arm_total_long_prov", "arm_total_short_prov",
                "pass_reason_code", "htf_warmup_ready"):
        if col in row.index and not _is_na(row[col]):
            v = row[col]
            detail[col] = bool(v) if col == "htf_warmup_ready" else (
                int(v) if col.endswith("_prov") or col == "pass_reason_code" else float(v)
            )
    return detail


def blocking_gates_for_direction(
    gate_state: dict[str, bool | None],
    direction: str,
    *,
    detail: dict[str, Any] | None = None,
) -> list[str]:
    """
    Gates that blocked TAKE. Skips evidence_threshold when state is insufficient_warmup/unknown_na.
    """
    side = direction.lower()
    blocked: list[str] = []
    chain = [
        f"armed_{side}",
        f"evidence_threshold_{side}",
        f"decide_e_{side}",
        f"p4_keep_{side}",
        f"h1_keep_{side}",
        "gate_open",
        "not_in_cooldown",
    ]
    ev_state = None
    if detail:
        ev_state = detail.get(f"evidence_threshold_{side}_state")

    for g in chain:
        if g not in gate_state:
            continue
        val = gate_state[g]
        if g == f"evidence_threshold_{side}":
            if ev_state in ("insufficient_warmup", "unknown_na"):
                continue
            if val is None:
                continue
        if val is False:
            blocked.append(g)
    return blocked
