"""Market state classifier — continuation / pullback / reversal / uncertain."""
from __future__ import annotations

from phase58e.research.active_move import side_aligned_with_active


def classify_market_state(
    original_direction: str,
    active: dict,
    struct: dict,
    counter: dict,
) -> tuple[str, list[str]]:
    """Causal market state at opportunity timestamp."""
    reasons: list[str] = []
    dom = active["dominant_active"]
    aligned = side_aligned_with_active(original_direction, active)

    ct_ratio = counter.get("countertrend_ratio", 0.0)
    pull_thr = counter.get("pullback_threshold", 0.5)
    rev_thr = counter.get("reversal_threshold", 0.85)

    prior_weakening = struct.get("prior_weakening", False)
    opp_strengthening = struct.get("opposite_strengthening", False)
    structure_intact = struct.get("structure_intact", False)

    if aligned and structure_intact and ct_ratio < pull_thr:
        reasons.extend(["ACTIVE_ALIGNED", "STRUCTURE_INTACT", "COUNTERTREND_WEAK"])
        return "CONTINUATION", reasons

    if not aligned and ct_ratio < pull_thr and structure_intact:
        reasons.extend(["COUNTERTREND_WEAK", "DOMINANT_MOVE_INTact"])
        dom_bull = dom in ("STRONG_UP", "UP")
        dom_bear = dom in ("STRONG_DOWN", "DOWN")
        if (dom_bull and original_direction == "SHORT") or (dom_bear and original_direction == "LONG"):
            reasons.append("PULLBACK_AGAINST_DOMINANT")
            return "PULLBACK", reasons

    if prior_weakening and opp_strengthening and ct_ratio >= rev_thr:
        reasons.extend(["PRIOR_MOVE_WEAKENING", "OPPOSITE_STRENGTHENING", "COUNTERTREND_STRONG"])
        return "REVERSAL_TRANSITION", reasons

    if not aligned and ct_ratio >= rev_thr:
        reasons.append("COUNTERTREND_STRONG")
        return "REVERSAL_TRANSITION", reasons

    if not aligned and ct_ratio >= pull_thr:
        reasons.append("PULLBACK_DEEP")
        return "PULLBACK", reasons

    reasons.append("INSUFFICIENT_EVIDENCE")
    return "UNCERTAIN", reasons
