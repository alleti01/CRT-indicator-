"""Phase66 — E1/E2/E3 price-action entry families at Phase58 locations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from phase66.python.levels import CausalLevels, build_levels

Family = Literal["E1", "E2", "E3"]
Timing = Literal["close", "next_open"]


@dataclass
class EntrySignal:
    family: str
    decision: str  # TAKE / PASS / CONFLICT / EXPIRED
    direction: str
    alarm_i: int
    trigger_i: int
    entry_i: int
    delay_bars: int
    reason: str
    level_name: str
    level_price: float
    invalidation: float
    chase_atr: float


def _bar(m, i: int):
    return float(m.op[i]), float(m.hi[i]), float(m.lo[i]), float(m.cl[i])


def detect_e1(m, lv: CausalLevels, atr: float) -> Optional[EntrySignal]:
    """Failed push / rejection at 5-bar micro extreme."""
    o, h, l, c = _bar(m, lv.eval_i)
    level = lv.hi_5
    # SHORT: probe above 5-bar high, close back below
    if h > level and c < level:
        inv = h
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E1", "TAKE", "SHORT", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E1_FAILED_PUSH_HIGH_SHORT", "hi_5", level, inv, chase,
        )
    level = lv.lo_5
    if l < level and c > level:
        inv = l
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E1", "TAKE", "LONG", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E1_FAILED_PUSH_LOW_LONG", "lo_5", level, inv, chase,
        )
    return None


def detect_e2(m, lv: CausalLevels, atr: float) -> Optional[EntrySignal]:
    """Break + acceptance above/below 5-bar level."""
    o, h, l, c = _bar(m, lv.eval_i)
    level = lv.hi_5
    if c > level and o <= level:
        inv = level
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E2", "TAKE", "LONG", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E2_BREAK_ACCEPT_HIGH_LONG", "hi_5", level, inv, chase,
        )
    level = lv.lo_5
    if c < level and o >= level:
        inv = level
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E2", "TAKE", "SHORT", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E2_BREAK_ACCEPT_LOW_SHORT", "lo_5", level, inv, chase,
        )
    return None


def detect_e3(m, lv: CausalLevels, atr: float) -> Optional[EntrySignal]:
    """Failed break + reclaim through 5-bar level."""
    o, h, l, c = _bar(m, lv.eval_i)
    level = lv.hi_5
    if h > level and c < level and o < level:
        inv = h
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E3", "TAKE", "SHORT", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E3_FAILED_BREAK_RECLAIM_HIGH_SHORT", "hi_5", level, inv, chase,
        )
    level = lv.lo_5
    if l < level and c > level and o > level:
        inv = l
        chase = abs(float(m.op[lv.eval_i + 1]) - lv.origin) / atr if lv.eval_i + 1 < m.n else 0
        return EntrySignal(
            "E3", "TAKE", "LONG", lv.alarm_i, lv.eval_i, lv.eval_i + 1,
            lv.eval_i - lv.alarm_i + 1, "E3_FAILED_BREAK_RECLAIM_LOW_LONG", "lo_5", level, inv, chase,
        )
    return None


DETECTORS = {"E1": detect_e1, "E2": detect_e2, "E3": detect_e3}


def scan_family(m, alarm_i: int, atr: float, family: str, max_delay: int = 3) -> EntrySignal:
    """First qualifying event in T0..T+max_delay."""
    a = atr if atr > 0 else 1.0
    fn = DETECTORS[family]
    signals = []
    for offset in range(0, max_delay + 1):
        eval_i = alarm_i + offset
        if eval_i + 2 >= m.n - 61:
            break
        lv = build_levels(m, alarm_i, eval_i)
        sig = fn(m, lv, a)
        if sig:
            signals.append(sig)
    if not signals:
        return EntrySignal(family, "EXPIRED", "", alarm_i, -1, -1, max_delay + 1, "PASS_NO_PRICE_ACTION", "", 0, 0, 0)
    dirs = {s.direction for s in signals}
    if len(dirs) > 1:
        return EntrySignal(family, "CONFLICT", "", alarm_i, -1, -1, signals[0].delay_bars, "PASS_CONFLICT", "", 0, 0, 0)
    return signals[0]
