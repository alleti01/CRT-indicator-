"""Phase63 — causal reaction detectors on frozen Phase58 opportunities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np

Decision = Literal["TAKE", "PASS", "WAIT", "NONE"]
Timing = Literal["T0", "T1", "T2"]


@dataclass
class ReactionResult:
    family: str
    timing: str
    decision: Decision
    direction: str  # LONG / SHORT / ""
    entry_i: int
    delay_bars: int
    reason: str
    reaction_dir: str  # implied reaction direction


def _bar(m, i: int) -> dict:
    i = int(np.clip(i, 0, m.n - 1))
    o, h, l, c = float(m.op[i]), float(m.hi[i]), float(m.lo[i]), float(m.cl[i])
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    return {"o": o, "h": h, "l": l, "c": c, "rng": rng, "body": body,
            "upper_wick": h - max(o, c), "lower_wick": min(o, c) - l}


def _atr(m, i: int, fallback: float) -> float:
    a = float(m.atr[i]) if np.isfinite(m.atr[i]) and m.atr[i] > 0 else fallback
    return a if a > 0 else 1.0


# ── R1 Rejection ─────────────────────────────────────────────────────────────
def r1_rejection(m, signal_i: int, orig_dir: str, atr: float, timing: Timing) -> ReactionResult:
    """Probe + reject: lower wick rejection → LONG, upper wick → SHORT."""
    eval_i = signal_i if timing == "T0" else signal_i + 1 if timing == "T1" else signal_i + 2
    entry_i = eval_i + 1
    if entry_i >= m.n - 61:
        return ReactionResult("R1", timing, "NONE", "", -1, 0, "OOB", "")
    b = _bar(m, eval_i)
    a = _atr(m, eval_i, atr)
    lower_pct = b["lower_wick"] / b["rng"]
    upper_pct = b["upper_wick"] / b["rng"]
    close_pos = (b["c"] - b["l"]) / b["rng"]
    if lower_pct >= 0.35 and close_pos >= 0.55:
        rd, reason = "LONG", "REJECTION_LOWER"
    elif upper_pct >= 0.35 and close_pos <= 0.45:
        rd, reason = "SHORT", "REJECTION_UPPER"
    else:
        return ReactionResult("R1", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_REJECTION", "")
    if rd == orig_dir:
        return ReactionResult("R1", timing, "TAKE", rd, entry_i, eval_i - signal_i, f"TAKE_ORIGINAL_{reason}", rd)
    return ReactionResult("R1", timing, "TAKE", rd, entry_i, eval_i - signal_i, f"TAKE_REVERSE_{reason}", rd)


# ── R2 Micro break ───────────────────────────────────────────────────────────
def r2_micro_break(m, signal_i: int, orig_dir: str, atr: float, timing: Timing) -> ReactionResult:
    eval_i = signal_i if timing == "T0" else signal_i + 1 if timing == "T1" else signal_i + 2
    entry_i = eval_i + 1
    if entry_i >= m.n - 61 or eval_i < 3:
        return ReactionResult("R2", timing, "NONE", "", -1, 0, "OOB", "")
    start = max(0, eval_i - 5)
    micro_hi = float(np.max(m.hi[start:eval_i]))
    micro_lo = float(np.min(m.lo[start:eval_i]))
    b = _bar(m, eval_i)
    if b["c"] > micro_hi:
        rd, reason = "LONG", "MICRO_BREAK_UP"
    elif b["c"] < micro_lo:
        rd, reason = "SHORT", "MICRO_BREAK_DN"
    else:
        return ReactionResult("R2", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_MICRO_BREAK", "")
    return ReactionResult("R2", timing, "TAKE", rd, entry_i, eval_i - signal_i, reason, rd)


# ── R3 Displacement ──────────────────────────────────────────────────────────
def r3_displacement(m, signal_i: int, orig_dir: str, atr: float, timing: Timing) -> ReactionResult:
    eval_i = signal_i if timing == "T0" else signal_i + 1 if timing == "T1" else signal_i + 2
    entry_i = eval_i + 1
    if entry_i >= m.n - 61:
        return ReactionResult("R3", timing, "NONE", "", -1, 0, "OOB", "")
    b = _bar(m, eval_i)
    a = _atr(m, eval_i, atr)
    origin = float(m.op[signal_i])
    ext = abs(b["c"] - origin) / a
    if b["body"] / a < 0.35:
        return ReactionResult("R3", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_DISPLACEMENT", "")
    if ext > 1.2:
        return ReactionResult("R3", timing, "PASS", "", entry_i, eval_i - signal_i, "TOO_EXTENDED", "")
    close_pos = (b["c"] - b["l"]) / b["rng"]
    if b["c"] > b["o"] and close_pos >= 0.65:
        rd = "LONG"
    elif b["c"] < b["o"] and close_pos <= 0.35:
        rd = "SHORT"
    else:
        return ReactionResult("R3", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_DISPLACEMENT", "")
    return ReactionResult("R3", timing, "TAKE", rd, entry_i, eval_i - signal_i, "DISPLACEMENT", rd)


# ── R4 Failure / reclaim ─────────────────────────────────────────────────────
def r4_failure_reclaim(m, signal_i: int, orig_dir: str, atr: float, timing: Timing) -> ReactionResult:
    eval_i = signal_i if timing == "T0" else signal_i + 1 if timing == "T1" else signal_i + 2
    entry_i = eval_i + 1
    if entry_i >= m.n - 61:
        return ReactionResult("R4", timing, "NONE", "", -1, 0, "OOB", "")
    origin = float(m.op[signal_i])
    b = _bar(m, eval_i)
    if orig_dir == "LONG":
        if b["l"] < origin and b["c"] > origin:
            return ReactionResult("R4", timing, "TAKE", "LONG", entry_i, eval_i - signal_i, "RECLAIM_ABOVE_ORIGIN", "LONG")
        if b["l"] < origin and b["c"] <= origin:
            return ReactionResult("R4", timing, "PASS", "", entry_i, eval_i - signal_i, "FAILED_RECLAIM", "")
    else:
        if b["h"] > origin and b["c"] < origin:
            return ReactionResult("R4", timing, "TAKE", "SHORT", entry_i, eval_i - signal_i, "RECLAIM_BELOW_ORIGIN", "SHORT")
        if b["h"] > origin and b["c"] >= origin:
            return ReactionResult("R4", timing, "PASS", "", entry_i, eval_i - signal_i, "FAILED_RECLAIM", "")
    return ReactionResult("R4", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_FAILURE_RECLAIM", "")


# ── R5 Immediate continuation ────────────────────────────────────────────────
def r5_continuation(m, signal_i: int, orig_dir: str, atr: float, timing: Timing) -> ReactionResult:
    eval_i = signal_i if timing == "T0" else signal_i + 1 if timing == "T1" else signal_i + 2
    entry_i = eval_i + 1
    if entry_i >= m.n - 61:
        return ReactionResult("R5", timing, "NONE", "", -1, 0, "OOB", "")
    b = _bar(m, eval_i)
    a = _atr(m, eval_i, atr)
    origin = float(m.op[signal_i])
    ext = abs(b["c"] - origin) / a
    if ext > 0.8:
        return ReactionResult("R5", timing, "PASS", "", entry_i, eval_i - signal_i, "TOO_EXTENDED", "")
    if orig_dir == "LONG" and b["c"] > b["o"] and b["body"] / a >= 0.2:
        return ReactionResult("R5", timing, "TAKE", "LONG", entry_i, eval_i - signal_i, "CONTINUATION", "LONG")
    if orig_dir == "SHORT" and b["c"] < b["o"] and b["body"] / a >= 0.2:
        return ReactionResult("R5", timing, "TAKE", "SHORT", entry_i, eval_i - signal_i, "CONTINUATION", "SHORT")
    return ReactionResult("R5", timing, "PASS", "", entry_i, eval_i - signal_i, "NO_CONTINUATION", "")


REACTION_FNS = {
    "R1": r1_rejection,
    "R2": r2_micro_break,
    "R3": r3_displacement,
    "R4": r4_failure_reclaim,
    "R5": r5_continuation,
}


def baseline_entry(signal_i: int, orig_dir: str, delay: int = 0) -> ReactionResult:
    """Baseline A (delay=0) or B (delay=1)."""
    entry_i = signal_i + 1 + delay
    return ReactionResult(
        "BASE", f"T{delay}", "TAKE", orig_dir, entry_i, delay,
        "BASELINE_ORIGINAL", orig_dir,
    )
