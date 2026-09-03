"""Phase65 — causal market-choice triggers after Phase58 alarm."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Concept = Literal["M1", "M2", "M3", "M4"]


@dataclass
class ChoiceResult:
    decision: str  # TAKE / EXPIRED
    direction: str
    choice_i: int
    entry_i: int
    delay_bars: int
    reason: str
    chase_atr: float


def _bar_range(m, i: int) -> float:
    return max(float(m.hi[i]) - float(m.lo[i]), 1e-9)


def _cum_excursion(m, signal_i: int, eval_i: int, origin: float, atr: float) -> tuple[float, float]:
    hs = m.hi[signal_i : eval_i + 1]
    ls = m.lo[signal_i : eval_i + 1]
    up = (float(hs.max()) - origin) / atr
    dn = (origin - float(ls.min())) / atr
    return up, dn


def _m1(m, eval_i: int, origin: float, atr: float, thr: float = 0.5) -> Optional[str]:
    up = (float(m.hi[eval_i]) - origin) / atr
    dn = (origin - float(m.lo[eval_i])) / atr
    if up >= thr and up >= dn:
        return "LONG"
    if dn >= thr and dn > up:
        return "SHORT"
    return None


def _m2(m, eval_i: int, origin: float, atr: float, thr: float = 0.5) -> Optional[str]:
    o, h, l, c = float(m.op[eval_i]), float(m.hi[eval_i]), float(m.lo[eval_i]), float(m.cl[eval_i])
    rng = max(h - l, 1e-9)
    up = (h - origin) / atr
    dn = (origin - l) / atr
    close_pos = (c - l) / rng
    if up >= thr and c > origin and close_pos >= 0.55:
        return "LONG"
    if dn >= thr and c < origin and close_pos <= 0.45:
        return "SHORT"
    return None


def _m3(m, signal_i: int, eval_i: int, origin: float, atr: float, thr: float = 0.5, max_giveback: float = 0.25) -> Optional[str]:
    up, dn = _cum_excursion(m, signal_i, eval_i, origin, atr)
    c = float(m.cl[eval_i])
    if up >= thr:
        peak = float(m.hi[signal_i : eval_i + 1].max())
        giveback = (peak - c) / atr
        if giveback <= max_giveback and c > origin:
            return "LONG"
    if dn >= thr:
        trough = float(m.lo[signal_i : eval_i + 1].min())
        giveback = (c - trough) / atr
        if giveback <= max_giveback and c < origin:
            return "SHORT"
    return None


def _m4(m, signal_i: int, eval_i: int, origin: float, atr: float, thr: float = 0.5, ratio: float = 1.5) -> Optional[str]:
    up, dn = _cum_excursion(m, signal_i, eval_i, origin, atr)
    if up >= thr and up >= dn * ratio:
        return "LONG"
    if dn >= thr and dn >= up * ratio:
        return "SHORT"
    return None


REASON = {
    "M1": {"LONG": "CHOICE_UP_DISPLACEMENT", "SHORT": "CHOICE_DOWN_DISPLACEMENT"},
    "M2": {"LONG": "CHOICE_UP_ACCEPTANCE", "SHORT": "CHOICE_DOWN_ACCEPTANCE"},
    "M3": {"LONG": "CHOICE_UP_LIMITED_RETRACE", "SHORT": "CHOICE_DOWN_LIMITED_RETRACE"},
    "M4": {"LONG": "CHOICE_UP_ONE_SIDED", "SHORT": "CHOICE_DOWN_ONE_SIDED"},
}


def scan_market_choice(
    m,
    signal_i: int,
    atr: float,
    concept: Concept,
    max_delay: int = 3,
    thr: float = 0.5,
) -> ChoiceResult:
    """Scan T0..T+max_delay; enter next bar after choice bar closes."""
    origin = float(m.op[signal_i])
    a = atr if atr > 0 else 1.0
    if signal_i + max_delay + 2 >= m.n - 61:
        return ChoiceResult("EXPIRED", "", -1, -1, max_delay + 1, "EXPIRE_NO_MARKET_CHOICE", 0.0)

    for offset in range(0, max_delay + 1):
        eval_i = signal_i + offset
        d: Optional[str] = None
        if concept == "M1":
            d = _m1(m, eval_i, origin, a, thr)
        elif concept == "M2":
            d = _m2(m, eval_i, origin, a, thr)
        elif concept == "M3":
            d = _m3(m, signal_i, eval_i, origin, a, thr)
        elif concept == "M4":
            d = _m4(m, signal_i, eval_i, origin, a, thr)
        if d:
            entry_i = eval_i + 1
            chase = abs(float(m.op[entry_i]) - origin) / a
            return ChoiceResult(
                "TAKE", d, eval_i, entry_i, offset + 1,
                REASON[concept][d], chase,
            )
    return ChoiceResult("EXPIRED", "", -1, -1, max_delay + 1, "EXPIRE_NO_MARKET_CHOICE", 0.0)


def naive_first_break(m, signal_i: int, atr: float, thr: float = 0.5) -> ChoiceResult:
    """Reference baseline B2/B3 — first touch of ±thr from origin."""
    origin = float(m.op[signal_i])
    a = atr if atr > 0 else 1.0
    end = min(signal_i + 61, m.n)
    for k in range(signal_i, end):
        up = (float(m.hi[k]) - origin) / a
        dn = (origin - float(m.lo[k])) / a
        hit_up = up >= thr
        hit_dn = dn >= thr
        if hit_up and not hit_dn:
            entry_i = k + 1 if k + 1 < m.n else k
            return ChoiceResult("TAKE", "LONG", k, entry_i, k - signal_i + 1, "NAIVE_FIRST_UP", abs(float(m.op[entry_i]) - origin) / a)
        if hit_dn and not hit_up:
            entry_i = k + 1 if k + 1 < m.n else k
            return ChoiceResult("TAKE", "SHORT", k, entry_i, k - signal_i + 1, "NAIVE_FIRST_DN", abs(float(m.op[entry_i]) - origin) / a)
        if hit_up and hit_dn:
            # same bar both — use open-to-close direction as tiebreak (causal at bar close)
            if float(m.cl[k]) >= origin:
                entry_i = k + 1 if k + 1 < m.n else k
                return ChoiceResult("TAKE", "LONG", k, entry_i, k - signal_i + 1, "NAIVE_TIE_UP", abs(float(m.op[entry_i]) - origin) / a)
            entry_i = k + 1 if k + 1 < m.n else k
            return ChoiceResult("TAKE", "SHORT", k, entry_i, k - signal_i + 1, "NAIVE_TIE_DN", abs(float(m.op[entry_i]) - origin) / a)
    return ChoiceResult("EXPIRED", "", -1, -1, 61, "EXPIRE_NO_BREAK", 0.0)
