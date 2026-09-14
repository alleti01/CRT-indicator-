"""Execution state machine — TAKE / WAIT / PASS with reason codes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from phase84.python.config import BODY_FRAC_THRESHOLDS, WAIT_BARS
from phase84.python.features import bucket_range_position


class ExecDecision(str, Enum):
    TAKE_BASELINE = "TAKE_BASELINE"
    TAKE_CLEAN = "TAKE_CLEAN"
    TAKE_ACCEPTANCE = "TAKE_ACCEPTANCE"
    TAKE_COMMITMENT = "TAKE_COMMITMENT"
    TAKE_AFTER_RESET = "TAKE_AFTER_RESET"
    TAKE_RETEST_HOLD = "TAKE_RETEST_HOLD"
    WAIT_EXTENSION = "WAIT_EXTENSION"
    WAIT_AMBIGUOUS = "WAIT_AMBIGUOUS"
    WAIT_RETEST = "WAIT_RETEST"
    PASS_CHASE = "PASS_CHASE"
    PASS_MID_RANGE = "PASS_MID_RANGE"
    PASS_FAILED_BREAK = "PASS_FAILED_BREAK"
    PASS_OPPOSITE_REACTION = "PASS_OPPOSITE_REACTION"
    PASS_NO_COMMITMENT = "PASS_NO_COMMITMENT"
    PASS_EXPIRED = "PASS_EXPIRED"


@dataclass
class ExecutionOutcome:
    decision: ExecDecision
    entry_i: int
    entry_delay_bars: int
    reason: str


def decide_e0() -> ExecutionOutcome:
    return ExecutionOutcome(ExecDecision.TAKE_BASELINE, entry_i=-1, entry_delay_bars=0, reason="E0 baseline")


def decide_e1_midrange(row: pd.Series, pass_mid: bool = False) -> ExecutionOutcome | None:
    rp = float(row.get("range_position_20", 0.5))
    bucket = bucket_range_position(rp)
    if pass_mid and bucket == "0.40-0.60":
        return ExecutionOutcome(ExecDecision.PASS_MID_RANGE, -1, 0, "mid_range_20")
    return None


def decide_e3_failed_break(row: pd.Series) -> ExecutionOutcome | None:
    if row.get("failed_break"):
        return ExecutionOutcome(ExecDecision.PASS_FAILED_BREAK, -1, 0, "failed_break_at_signal")
    return None


def decide_e4_extension(row: pd.Series, chase_atr: float = 1.5) -> ExecutionOutcome | None:
    ext = float(row.get("move_5m_ATR", 0))
    if ext >= chase_atr:
        return ExecutionOutcome(ExecDecision.PASS_CHASE, -1, 0, f"extension_5m>={chase_atr}")
    return None


def decide_e2_acceptance(row: pd.Series, require: bool = False) -> ExecutionOutcome | None:
    if require and not row.get("break_close_accept"):
        return ExecutionOutcome(ExecDecision.PASS_NO_COMMITMENT, -1, 0, "no_close_acceptance")
    if row.get("break_close_accept"):
        return ExecutionOutcome(ExecDecision.TAKE_ACCEPTANCE, -1, 0, "close_acceptance")
    return None


def decide_e6_commitment(row: pd.Series, body_frac_min: float = 0.55) -> ExecutionOutcome | None:
    if float(row.get("signal_body_frac", 0)) >= body_frac_min and float(row.get("directional_body_ATR", 0)) > 0.3:
        return ExecutionOutcome(ExecDecision.TAKE_COMMITMENT, -1, 0, "immediate_commitment")
    return None


def apply_variant(row: pd.Series, variant: str, params: dict | None = None) -> ExecutionOutcome:
    params = params or {}
    baseline_entry_i = int(row["entry_i"])

    if variant == "E0":
        return ExecutionOutcome(ExecDecision.TAKE_BASELINE, baseline_entry_i, 0, "E0")

    if variant == "E1":
        hit = decide_e1_midrange(row, pass_mid=params.get("pass_mid", True))
        if hit:
            return hit
        return ExecutionOutcome(ExecDecision.TAKE_CLEAN, baseline_entry_i, 0, "E1_no_mid_filter")

    if variant == "E2":
        if not row.get("break_close_accept"):
            return ExecutionOutcome(ExecDecision.PASS_NO_COMMITMENT, -1, 0, "E2_no_acceptance")
        return ExecutionOutcome(ExecDecision.TAKE_ACCEPTANCE, baseline_entry_i, 0, "E2_acceptance")

    if variant == "E3":
        hit = decide_e3_failed_break(row)
        if hit:
            return hit
        return ExecutionOutcome(ExecDecision.TAKE_CLEAN, baseline_entry_i, 0, "E3_no_failure")

    if variant == "E4":
        hit = decide_e4_extension(row, chase_atr=params.get("chase_atr", 1.5))
        if hit:
            return hit
        return ExecutionOutcome(ExecDecision.TAKE_CLEAN, baseline_entry_i, 0, "E4_not_extended")

    if variant == "E6":
        hit = decide_e6_commitment(row, body_frac_min=params.get("body_frac", 0.55))
        if hit:
            return ExecutionOutcome(ExecDecision.TAKE_COMMITMENT, baseline_entry_i, 0, "E6_commit")
        return ExecutionOutcome(ExecDecision.PASS_NO_COMMITMENT, -1, 0, "E6_no_commitment")

    return ExecutionOutcome(ExecDecision.TAKE_BASELINE, baseline_entry_i, 0, "unknown_variant")
