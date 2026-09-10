"""Phase82 entry decision engine."""
from __future__ import annotations

from dataclasses import dataclass

from phase82.python.m1_state import m1_features_at, scan_reset_entry
from phase82.python.m15_causal import M15CausalArrays
from phase82.python.m15_state import m15_state_at


@dataclass
class Decision:
    action: str  # TAKE, WAIT, PASS
    reason: str
    entry_type: str
    entry_i: int | None = None


def _m15_aligns(direction: str, m15: dict) -> bool:
    st = m15["m15_state"]
    if direction == "LONG":
        return st in ("15M_BULLISH", "15M_TRANSITION_UP", "15M_EXTENDED_UP", "15M_BALANCED")
    return st in ("15M_BEARISH", "15M_TRANSITION_DOWN", "15M_EXTENDED_DOWN", "15M_BALANCED")


def _m15_soft_ok(direction: str, m15: dict) -> bool:
    st = m15["m15_state"]
    if direction == "LONG":
        return st not in ("15M_BEARISH", "15M_EXTENDED_DOWN")
    return st not in ("15M_BULLISH", "15M_EXTENDED_UP")


def _is_extended_chase(direction: str, m15: dict, m1: dict) -> bool:
    if direction == "LONG":
        return m15["m15_state"] == "15M_EXTENDED_UP" or m1.get("m1_ext_up", False)
    return m15["m15_state"] == "15M_EXTENDED_DOWN" or m1.get("m1_ext_down", False)


def decide(
    arr: M15CausalArrays,
    sig_i: int,
    direction: str,
    model: str,
    *,
    ext_atr: float = 1.0,
    wait_for_reset: bool = False,
    allow_reversal: bool = False,
    use_memory: bool = False,
    seen_opps: set | None = None,
) -> Decision:
    """Decision at signal bar sig_i for baseline direction."""
    m15 = m15_state_at(arr, sig_i, ext_atr)
    m1 = m1_features_at(arr, sig_i)
    entry_i = sig_i + 1
    opp_key = (direction, m15["m15_state"], sig_i // 15)
    if use_memory and seen_opps is not None and opp_key in seen_opps:
        return Decision("PASS", "DUPLICATE_OPPORTUNITY", "NONE")

    if model in ("P0",):
        return Decision("TAKE", "BASELINE", "CONTINUATION_" + direction, entry_i)

    # 1M-only commitment gate
    m1_ok_long = m1.get("commitment_long") or m1.get("reaction_long") or m1.get("m1_state") in ("WATCH_LONG", "LONG_READY")
    m1_ok_short = m1.get("commitment_short") or m1.get("reaction_short") or m1.get("m1_state") in ("WATCH_SHORT", "SHORT_READY")

    if model == "P1":
        if direction == "LONG" and m1_ok_long:
            return Decision("TAKE", "TAKE_LONG_1M_COMMIT", "CONTINUATION_LONG", entry_i)
        if direction == "SHORT" and m1_ok_short:
            return Decision("TAKE", "TAKE_SHORT_1M_COMMIT", "CONTINUATION_SHORT", entry_i)
        return Decision("PASS", "PASS_NO_REACTION", "NONE")

    if model == "P2":
        if not _m15_aligns(direction, m15):
            return Decision("PASS", "PASS_15M_MISALIGN", "NONE")
        if direction == "LONG" and m1_ok_long:
            return Decision("TAKE", "TAKE_LONG_15M_ALIGN", "CONTINUATION_LONG", entry_i)
        if direction == "SHORT" and m1_ok_short:
            return Decision("TAKE", "TAKE_SHORT_15M_ALIGN", "CONTINUATION_SHORT", entry_i)
        return Decision("PASS", "PASS_NO_REACTION", "NONE")

    soft = model in ("P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10")
    hard_pass_ext = model == "P4"
    wait_reset = model in ("P5", "P6", "P7", "P8", "P9", "P10")
    need_cont = model in ("P6", "P8", "P9", "P10")
    need_rev = model in ("P7", "P8", "P9", "P10") and allow_reversal

    if soft and not _m15_soft_ok(direction, m15):
        if need_rev and allow_reversal:
            opp = "SHORT" if direction == "LONG" else "LONG"
            rev_m1 = m1.get("commitment_short") if opp == "SHORT" else m1.get("commitment_long")
            if rev_m1:
                return Decision("TAKE", f"TAKE_REVERSAL_{opp}", f"REVERSAL_{opp}", entry_i)
        return Decision("PASS", "PASS_CONFLICT", "NONE")

    extended = _is_extended_chase(direction, m15, m1)
    if extended:
        if hard_pass_ext:
            return Decision("PASS", "PASS_CHASE", "NONE")
        if wait_reset or wait_for_reset:
            ei, etype = scan_reset_entry(arr, sig_i, direction)
            if ei is not None:
                return Decision("TAKE", "WAIT_FOR_RESET", etype, ei)
            return Decision("PASS", "PASS_NO_RESET", "NONE")

    if need_cont:
        if direction == "LONG" and not (m1.get("pullback_from_high_atr", 0) >= 0.15 or m1_ok_long):
            return Decision("PASS", "WAIT_FOR_PULLBACK", "NONE")
        if direction == "SHORT" and not (m1.get("pullback_from_low_atr", 0) >= 0.15 or m1_ok_short):
            return Decision("PASS", "WAIT_FOR_PULLBACK", "NONE")

    if model == "P10":
        if not (m1.get("commitment_long") or m1.get("commitment_short")):
            return Decision("PASS", "WAIT_FOR_COMMITMENT", "NONE")
        if extended:
            ei, etype = scan_reset_entry(arr, sig_i, direction)
            if ei is None:
                return Decision("PASS", "PASS_NO_RESET", "NONE")
            entry_i = ei

    if direction == "LONG":
        if m1_ok_long or model in ("P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"):
            d = Decision("TAKE", "TAKE_LONG_15M_SOFT", "CONTINUATION_LONG", entry_i)
            if use_memory and seen_opps is not None:
                seen_opps.add(opp_key)
            return d
    else:
        if m1_ok_short or model in ("P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"):
            d = Decision("TAKE", "TAKE_SHORT_15M_SOFT", "CONTINUATION_SHORT", entry_i)
            if use_memory and seen_opps is not None:
                seen_opps.add(opp_key)
            return d

    return Decision("PASS", "PASS_NO_REACTION", "NONE")
