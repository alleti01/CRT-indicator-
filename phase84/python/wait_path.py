"""Causal WAIT / RESET / RETEST bar-path simulation for E5 and E7."""
from __future__ import annotations

import numpy as np

from phase84.python.config import WAIT_BARS
from phase84.python.features import compute_features_at_signal
from phase84.python.state_machine import ExecDecision, ExecutionOutcome


def _dir_sign(direction: str) -> int:
    return 1 if direction == "LONG" else -1


def _atr(atr: np.ndarray, i: int) -> float:
    v = float(atr[i])
    return v if v > 0 else 1.0


def decide_e5_wait_reset(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_i: int,
    direction: str,
    baseline_entry_i: int,
    max_wait: int = 3,
    chase_atr: float = 1.5,
    reset_atr: float = 0.5,
) -> ExecutionOutcome:
    """WAIT when extended at signal; recheck up to max_wait bars causally."""
    d = _dir_sign(direction)
    atr_t = _atr(atr, signal_i)

    ext = 0.0
    if signal_i >= 5:
        ext = (float(cl[signal_i]) - float(cl[signal_i - 5])) * d / atr_t

    if ext < 0.8:
        return ExecutionOutcome(
            ExecDecision.TAKE_BASELINE,
            baseline_entry_i,
            0,
            "E5_not_extended_take_now",
        )

    for w in range(1, max_wait + 1):
        i = signal_i + w
        if i >= len(cl) - 2:
            return ExecutionOutcome(ExecDecision.PASS_EXPIRED, -1, w, "E5_data_end")

        move = (float(cl[i]) - float(cl[signal_i])) * d / atr_t
        if move >= chase_atr:
            return ExecutionOutcome(ExecDecision.PASS_CHASE, -1, w, f"E5_chase_bar_{w}")

        bar_reaction = (float(cl[i]) - float(cl[i - 1])) * d
        if move <= reset_atr and bar_reaction > 0:
            return ExecutionOutcome(
                ExecDecision.TAKE_AFTER_RESET,
                i + 1,
                w,
                f"E5_reset_bar_{w}",
            )

        feats = compute_features_at_signal(hi, lo, cl, op, atr, i, direction)
        if feats.get("failed_break"):
            return ExecutionOutcome(
                ExecDecision.PASS_FAILED_BREAK,
                -1,
                w,
                f"E5_failed_reaction_bar_{w}",
            )

    return ExecutionOutcome(ExecDecision.PASS_EXPIRED, -1, max_wait, "E5_wait_expired")


def decide_e7_retest_hold(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    op: np.ndarray,
    atr: np.ndarray,
    signal_i: int,
    direction: str,
    baseline_entry_i: int,
    max_wait: int = 3,
    retest_tol_atr: float = 0.15,
) -> ExecutionOutcome:
    """Impulse at signal, causal retest of pre-signal level, hold, then enter."""
    d = _dir_sign(direction)
    sig_feats = compute_features_at_signal(hi, lo, cl, op, atr, signal_i, direction)
    atr_t = _atr(atr, signal_i)

    if d == 1:
        ref = float(sig_feats["local_high_pre"])
        impulse = bool(sig_feats["break_close_accept"]) or float(sig_feats.get("move_3m_ATR", 0)) > 0.3
    else:
        ref = float(sig_feats["local_low_pre"])
        impulse = bool(sig_feats["break_close_accept"]) or float(sig_feats.get("move_3m_ATR", 0)) > 0.3

    if not impulse:
        return ExecutionOutcome(
            ExecDecision.PASS_NO_COMMITMENT,
            -1,
            0,
            "E7_no_impulse",
        )

    tol = retest_tol_atr * atr_t
    for w in range(1, max_wait + 1):
        i = signal_i + w
        if i >= len(cl) - 2:
            return ExecutionOutcome(ExecDecision.PASS_EXPIRED, -1, w, "E7_data_end")

        if d == 1:
            touched = float(lo[i]) <= ref + tol
            held = float(cl[i]) >= ref - tol
            resume = float(cl[i]) > float(cl[i - 1])
        else:
            touched = float(hi[i]) >= ref - tol
            held = float(cl[i]) <= ref + tol
            resume = float(cl[i]) < float(cl[i - 1])

        if touched and held and resume:
            return ExecutionOutcome(
                ExecDecision.TAKE_RETEST_HOLD,
                i + 1,
                w,
                f"E7_retest_hold_bar_{w}",
            )

    return ExecutionOutcome(ExecDecision.PASS_EXPIRED, -1, max_wait, "E7_no_retest")


def classify_wait_attribution(
    baseline_r: float,
    delayed_r: float,
    baseline_mfe_before_delay: float = 0.0,
) -> str:
    delta = delayed_r - baseline_r
    if abs(delta) < 0.05:
        return "WAIT_NO_CHANGE"
    if delta > 0.05:
        return "WAIT_IMPROVED"
    if baseline_r > 0 and delayed_r <= 0:
        return "WAIT_MISSED_WINNER"
    if baseline_r <= 0 and delayed_r > baseline_r:
        return "WAIT_AVOIDED_LOSER"
    return "WAIT_HARMED"
