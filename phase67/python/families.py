"""Phase67 — setup families A–E state machines."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np

from phase67.python.precompute import MarketPre

Direction = Literal["LONG", "SHORT"]
Family = Literal["A", "B", "C", "D", "E"]


@dataclass
class SetupSignal:
    family: str
    variant: str
    direction: Direction
    setup_i: int
    trigger_i: int
    entry_i: int
    delay_bars: int
    origin_price: float
    invalidation: float
    chase_atr: float
    level_name: str
    level_price: float
    reason: str
    transitions: list[str] = field(default_factory=list)


def _atr(p: MarketPre, i: int) -> float:
    a = float(p.atr[i])
    return a if a > 0 else 1.0


def _entry_from_trigger(p: MarketPre, trigger_i: int, timing: str = "next_open") -> int:
    return trigger_i if timing == "close" else trigger_i + 1


def cluster_episodes(signals: list[SetupSignal], gap: int = 30) -> list[SetupSignal]:
    """First entry per same-direction episode."""
    if not signals:
        return []
    sigs = sorted(signals, key=lambda s: s.entry_i)
    out = []
    last_end = -10**9
    last_dir = ""
    for s in sigs:
        if s.direction != last_dir or s.setup_i - last_end > gap:
            out.append(s)
            last_dir = s.direction
        last_end = s.entry_i
    return out


# ---------------------------------------------------------------------------
# Family A — EXPANSION → PULLBACK → RESUMPTION
# ---------------------------------------------------------------------------
def scan_family_a(p: MarketPre, timing: str = "next_open", max_pullback_bars: int = 15) -> list[SetupSignal]:
    signals = []
    state = "IDLE"
    direction: Optional[Direction] = None
    exp_i = 0
    origin = 0.0
    running_ext = 0.0
    pullback_ext = 0.0
    leg = 0.0

    for i in range(25, p.n - 65):
        a = _atr(p, i)
        if state == "IDLE":
            # upward expansion
            if np.isfinite(p.lo_10[i]) and p.cl[i] - p.lo_10[i] >= 1.0 * a and p.cl[i] > p.op[i]:
                state = "EXPANSION"
                direction = "LONG"
                exp_i = i
                origin = float(p.lo_10[i])
                running_ext = float(p.hi[i])
                leg = running_ext - origin
                continue
            if np.isfinite(p.hi_10[i]) and p.hi_10[i] - p.cl[i] >= 1.0 * a and p.cl[i] < p.op[i]:
                state = "EXPANSION"
                direction = "SHORT"
                exp_i = i
                origin = float(p.hi_10[i])
                running_ext = float(p.lo[i])
                leg = origin - running_ext
                continue
        elif state == "EXPANSION" and direction:
            if i - exp_i > max_pullback_bars:
                state = "IDLE"
                continue
            if direction == "LONG":
                running_ext = max(running_ext, float(p.hi[i]))
                leg = running_ext - origin
                if leg >= 0.5 * a and p.cl[i] < running_ext - 0.25 * a:
                    state = "PULLBACK"
                    pullback_ext = float(p.lo[i])
            else:
                running_ext = min(running_ext, float(p.lo[i]))
                leg = origin - running_ext
                if leg >= 0.5 * a and p.cl[i] > running_ext + 0.25 * a:
                    state = "PULLBACK"
                    pullback_ext = float(p.hi[i])
        elif state == "PULLBACK" and direction:
            if i - exp_i > max_pullback_bars:
                state = "IDLE"
                continue
            if direction == "LONG":
                pullback_ext = min(pullback_ext, float(p.lo[i]))
                retrace = running_ext - pullback_ext
                if retrace > 0.75 * leg:
                    state = "IDLE"
                    continue
                if p.cl[i] > p.hi[i - 1]:
                    inv = pullback_ext
                    ei = _entry_from_trigger(p, i, timing)
                    if ei >= p.n - 61:
                        state = "IDLE"
                        continue
                    chase = abs(float(p.op[ei]) - origin) / a
                    signals.append(SetupSignal(
                        "A", "A10", "LONG", exp_i, i, ei, ei - exp_i, origin, inv, chase,
                        "exp_origin", origin, "A_RESUMPTION_LONG",
                        ["EXPANSION", "PULLBACK", "RESUMPTION"],
                    ))
                    state = "IDLE"
            else:
                pullback_ext = max(pullback_ext, float(p.hi[i]))
                retrace = pullback_ext - running_ext
                if retrace > 0.75 * leg:
                    state = "IDLE"
                    continue
                if p.cl[i] < p.lo[i - 1]:
                    inv = pullback_ext
                    ei = _entry_from_trigger(p, i, timing)
                    if ei >= p.n - 61:
                        state = "IDLE"
                        continue
                    chase = abs(float(p.op[ei]) - origin) / a
                    signals.append(SetupSignal(
                        "A", "A10", "SHORT", exp_i, i, ei, ei - exp_i, origin, inv, chase,
                        "exp_origin", origin, "A_RESUMPTION_SHORT",
                        ["EXPANSION", "PULLBACK", "RESUMPTION"],
                    ))
                    state = "IDLE"
    return cluster_episodes(signals)


# ---------------------------------------------------------------------------
# Family B — SWEEP → DISPLACEMENT → RETEST
# ---------------------------------------------------------------------------
def scan_family_b(p: MarketPre, level_bars: int = 10, timing: str = "next_open",
                  disp_atr: float = 0.5, max_wait: int = 20) -> list[SetupSignal]:
    hi_lvl = {5: p.hi_5, 10: p.hi_10, 20: p.hi_20}[level_bars]
    lo_lvl = {5: p.lo_5, 10: p.lo_10, 20: p.lo_20}[level_bars]
    variant = f"B{level_bars}"
    signals = []
    state = "IDLE"
    direction: Optional[Direction] = None
    sweep_i = 0
    level = 0.0
    disp_origin = 0.0

    for i in range(25, p.n - 65):
        a = _atr(p, i)
        if state == "IDLE":
            if np.isfinite(hi_lvl[i]) and p.hi[i] > hi_lvl[i] and p.cl[i] < hi_lvl[i]:
                state = "SWEPT"
                direction = "SHORT"
                sweep_i = i
                level = float(hi_lvl[i])
                continue
            if np.isfinite(lo_lvl[i]) and p.lo[i] < lo_lvl[i] and p.cl[i] > lo_lvl[i]:
                state = "SWEPT"
                direction = "LONG"
                sweep_i = i
                level = float(lo_lvl[i])
                continue
        elif state == "SWEPT" and direction:
            if i - sweep_i > max_wait:
                state = "IDLE"
                continue
            if direction == "SHORT" and p.cl[i] <= level - disp_atr * a:
                state = "DISPLACED"
                disp_origin = float(p.cl[i])
                continue
            if direction == "LONG" and p.cl[i] >= level + disp_atr * a:
                state = "DISPLACED"
                disp_origin = float(p.cl[i])
                continue
        elif state == "DISPLACED" and direction:
            if i - sweep_i > max_wait:
                state = "IDLE"
                continue
            if direction == "SHORT":
                if p.lo[i] <= level + 0.15 * a and p.cl[i] <= level + 0.1 * a:
                    inv = float(p.hi[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - disp_origin) / a
                        signals.append(SetupSignal(
                            "B", variant, "SHORT", sweep_i, i, ei, ei - sweep_i,
                            disp_origin, inv, chase, f"hi_{level_bars}", level,
                            f"B_HOLD_SHORT_{level_bars}",
                            ["SWEEP", "DISPLACEMENT", "RETEST"],
                        ))
                    state = "IDLE"
            else:
                if p.hi[i] >= level - 0.15 * a and p.cl[i] >= level - 0.1 * a:
                    inv = float(p.lo[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - disp_origin) / a
                        signals.append(SetupSignal(
                            "B", variant, "LONG", sweep_i, i, ei, ei - sweep_i,
                            disp_origin, inv, chase, f"lo_{level_bars}", level,
                            f"B_HOLD_LONG_{level_bars}",
                            ["SWEEP", "DISPLACEMENT", "RETEST"],
                        ))
                    state = "IDLE"
    return cluster_episodes(signals)


# ---------------------------------------------------------------------------
# Family C — COMPRESSION → EXPANSION → RETEST
# ---------------------------------------------------------------------------
def scan_family_c(p: MarketPre, range_bars: int = 10, timing: str = "next_open",
                  max_wait: int = 25) -> list[SetupSignal]:
    rng = {5: p.range_5, 10: p.range_10, 20: p.range_20}[range_bars]
    hi_lvl = {5: p.hi_5, 10: p.hi_10, 20: p.hi_20}[range_bars]
    lo_lvl = {5: p.lo_5, 10: p.lo_10, 20: p.lo_20}[range_bars]
    variant = f"C{range_bars}"
    signals = []
    state = "IDLE"
    direction: Optional[Direction] = None
    comp_i = 0
    frozen_hi = frozen_lo = 0.0

    for i in range(25, p.n - 65):
        a = _atr(p, i)
        if state == "IDLE":
            if np.isfinite(rng[i]) and rng[i] <= 2.0 * a:
                state = "COMPRESSION"
                comp_i = i
                frozen_hi = float(hi_lvl[i])
                frozen_lo = float(lo_lvl[i])
                continue
        elif state == "COMPRESSION":
            if i - comp_i > 5:
                state = "IDLE"
                continue
            if p.cl[i] > frozen_hi and p.op[i] <= frozen_hi:
                state = "BROKE"
                direction = "LONG"
                comp_i = i
                continue
            if p.cl[i] < frozen_lo and p.op[i] >= frozen_lo:
                state = "BROKE"
                direction = "SHORT"
                comp_i = i
                continue
        elif state == "BROKE" and direction:
            if i - comp_i > max_wait:
                state = "IDLE"
                continue
            if direction == "LONG":
                if p.lo[i] <= frozen_hi + 0.1 * a and p.cl[i] >= frozen_hi:
                    inv = float(p.lo[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - frozen_hi) / a
                        signals.append(SetupSignal(
                            "C", variant, "LONG", comp_i, i, ei, ei - comp_i,
                            frozen_hi, inv, chase, f"range_hi_{range_bars}", frozen_hi,
                            "C_HOLD_LONG", ["COMPRESSION", "BREAK", "RETEST"],
                        ))
                    state = "IDLE"
            else:
                if p.hi[i] >= frozen_lo - 0.1 * a and p.cl[i] <= frozen_lo:
                    inv = float(p.hi[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - frozen_lo) / a
                        signals.append(SetupSignal(
                            "C", variant, "SHORT", comp_i, i, ei, ei - comp_i,
                            frozen_lo, inv, chase, f"range_lo_{range_bars}", frozen_lo,
                            "C_HOLD_SHORT", ["COMPRESSION", "BREAK", "RETEST"],
                        ))
                    state = "IDLE"
    return cluster_episodes(signals)


# ---------------------------------------------------------------------------
# Family D — FAILED AUCTION → DISPLACEMENT → RETEST
# ---------------------------------------------------------------------------
def scan_family_d(p: MarketPre, level_bars: int = 10, timing: str = "next_open",
                  disp_atr: float = 0.5, max_wait: int = 25) -> list[SetupSignal]:
    hi_lvl = {5: p.hi_5, 10: p.hi_10, 20: p.hi_20}[level_bars]
    lo_lvl = {5: p.lo_5, 10: p.lo_10, 20: p.lo_20}[level_bars]
    signals = []
    state = "IDLE"
    direction: Optional[Direction] = None
    fail_i = 0
    level = 0.0
    base = 0.0

    for i in range(25, p.n - 65):
        a = _atr(p, i)
        if state == "IDLE":
            if np.isfinite(hi_lvl[i]) and p.hi[i] > hi_lvl[i] and p.cl[i] < hi_lvl[i]:
                state = "FAILED"
                direction = "SHORT"
                fail_i = i
                level = float(hi_lvl[i])
                continue
            if np.isfinite(lo_lvl[i]) and p.lo[i] < lo_lvl[i] and p.cl[i] > lo_lvl[i]:
                state = "FAILED"
                direction = "LONG"
                fail_i = i
                level = float(lo_lvl[i])
                continue
        elif state == "FAILED" and direction:
            if i - fail_i > max_wait:
                state = "IDLE"
                continue
            if direction == "SHORT" and p.cl[i] <= level - disp_atr * a:
                state = "DISPLACED"
                base = float(p.cl[i])
                continue
            if direction == "LONG" and p.cl[i] >= level + disp_atr * a:
                state = "DISPLACED"
                base = float(p.cl[i])
                continue
        elif state == "DISPLACED" and direction:
            if i - fail_i > max_wait:
                state = "IDLE"
                continue
            if direction == "SHORT":
                if p.lo[i] <= base + 0.25 * a and p.cl[i] < base + 0.15 * a:
                    inv = float(p.hi[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - base) / a
                        signals.append(SetupSignal(
                            "D", "D10", "SHORT", fail_i, i, ei, ei - fail_i,
                            base, inv, chase, f"fail_hi_{level_bars}", level,
                            "D_RETEST_SHORT", ["FAILED_AUCTION", "DISPLACEMENT", "RETEST"],
                        ))
                    state = "IDLE"
            else:
                if p.hi[i] >= base - 0.25 * a and p.cl[i] > base - 0.15 * a:
                    inv = float(p.lo[i])
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - base) / a
                        signals.append(SetupSignal(
                            "D", "D10", "LONG", fail_i, i, ei, ei - fail_i,
                            base, inv, chase, f"fail_lo_{level_bars}", level,
                            "D_RETEST_LONG", ["FAILED_AUCTION", "DISPLACEMENT", "RETEST"],
                        ))
                    state = "IDLE"
    return cluster_episodes(signals)


# ---------------------------------------------------------------------------
# Family E — STRUCTURE BREAK → RETRACE → SECOND IMPULSE
# ---------------------------------------------------------------------------
def scan_family_e(p: MarketPre, level_bars: int = 10, timing: str = "next_open",
                  max_wait: int = 25) -> list[SetupSignal]:
    hi_lvl = {5: p.hi_5, 10: p.hi_10, 20: p.hi_20}[level_bars]
    lo_lvl = {5: p.lo_5, 10: p.lo_10, 20: p.lo_20}[level_bars]
    signals = []
    state = "IDLE"
    direction: Optional[Direction] = None
    break_i = 0
    level = 0.0
    retrace_ext = 0.0

    for i in range(25, p.n - 65):
        a = _atr(p, i)
        if state == "IDLE":
            if np.isfinite(hi_lvl[i]) and p.cl[i] > hi_lvl[i]:
                state = "BROKE"
                direction = "LONG"
                break_i = i
                level = float(hi_lvl[i])
                retrace_ext = float(p.lo[i])
                continue
            if np.isfinite(lo_lvl[i]) and p.cl[i] < lo_lvl[i]:
                state = "BROKE"
                direction = "SHORT"
                break_i = i
                level = float(lo_lvl[i])
                retrace_ext = float(p.hi[i])
                continue
        elif state == "BROKE" and direction:
            if i - break_i > max_wait:
                state = "IDLE"
                continue
            if direction == "LONG":
                retrace_ext = min(retrace_ext, float(p.lo[i]))
                if p.cl[i] < level:
                    state = "IDLE"
                    continue
                if p.cl[i] > p.hi[i - 1] and p.cl[i] > retrace_ext + 0.25 * a:
                    inv = retrace_ext
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - level) / a
                        signals.append(SetupSignal(
                            "E", "E10", "LONG", break_i, i, ei, ei - break_i,
                            level, inv, chase, f"struct_hi_{level_bars}", level,
                            "E_SECOND_IMPULSE_LONG", ["BREAK", "RETRACE", "IMPULSE"],
                        ))
                    state = "IDLE"
            else:
                retrace_ext = max(retrace_ext, float(p.hi[i]))
                if p.cl[i] > level:
                    state = "IDLE"
                    continue
                if p.cl[i] < p.lo[i - 1] and p.cl[i] < retrace_ext - 0.25 * a:
                    inv = retrace_ext
                    ei = _entry_from_trigger(p, i, timing)
                    if ei < p.n - 61:
                        chase = abs(float(p.op[ei]) - level) / a
                        signals.append(SetupSignal(
                            "E", "E10", "SHORT", break_i, i, ei, ei - break_i,
                            level, inv, chase, f"struct_lo_{level_bars}", level,
                            "E_SECOND_IMPULSE_SHORT", ["BREAK", "RETRACE", "IMPULSE"],
                        ))
                    state = "IDLE"
    return cluster_episodes(signals)


SCANNERS = {
    "A": lambda p: scan_family_a(p),
    "B10": lambda p: scan_family_b(p, 10),
    "B5": lambda p: scan_family_b(p, 5),
    "B20": lambda p: scan_family_b(p, 20),
    "C": lambda p: scan_family_c(p, 10),
    "D": lambda p: scan_family_d(p, 10),
    "E": lambda p: scan_family_e(p, 10),
}
