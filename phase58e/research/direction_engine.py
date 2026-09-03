"""Two-sided direction engine — continuation / reversal scores, variants D0-D4."""
from __future__ import annotations

from phase58b.research.precompute import MTFArrays
from phase58d.research.context_maps import ctx15_at_1m, location_score
from phase58e.research.active_move import active_move_at_bar, side_aligned_with_active, _score_state
from phase58e.research.market_state import classify_market_state
from phase58e.research.structure import countertrend_strength, structural_features, structure_context


def score_side(
    direction: str,
    m: MTFArrays,
    i: int,
    active: dict,
    struct: dict,
    counter: dict,
    loc_score: int,
    cfg: dict,
) -> dict:
    """Continuation and reversal scores for one direction."""
    ctx = structure_context(struct, active, direction)
    aligned = side_aligned_with_active(direction, active)
    reasons: list[str] = []

    cont = 0
    rev = 0

    dom_sc = _score_state(active["dominant_active"])
    if direction == "LONG":
        cont += max(0, dom_sc)
        rev += max(0, -dom_sc)
        if dom_sc >= 1:
            reasons.append("ACTIVE_UP_STRONG" if dom_sc == 2 else "ACTIVE_UP")
        if struct["bull_structure"]:
            cont += 1
            reasons.append("STRUCTURE_UP_INTACT")
        if struct["failed_down_extension"]:
            rev += 1
            reasons.append("FAILED_DOWN_EXTENSION")
    else:
        cont += max(0, -dom_sc)
        rev += max(0, dom_sc)
        if dom_sc <= -1:
            reasons.append("ACTIVE_DOWN_STRONG" if dom_sc == -2 else "ACTIVE_DOWN")
        if struct["bear_structure"]:
            cont += 1
            reasons.append("STRUCTURE_DOWN_INTACT")
        if struct["failed_up_extension"]:
            rev += 1
            reasons.append("FAILED_UP_EXTENSION")

    ct = counter.get("countertrend_ratio", 0.0)
    if ct < cfg.get("countertrend_ratio_pullback", 0.5):
        cont += 1
        reasons.append("COUNTERTREND_WEAK")
    elif ct >= cfg.get("countertrend_ratio_reversal", 0.85):
        rev += 2
        reasons.append("COUNTERTREND_STRONG")
    else:
        reasons.append("PULLBACK_MODERATE")

    if ctx["prior_weakening"]:
        rev += 1
        reasons.append("PRIOR_MOVE_EXHAUSTING")
    if ctx["opposite_strengthening"]:
        rev += 1
        reasons.append("OPPOSITE_STRENGTHENING")

    if aligned:
        cont += 1
        reasons.append(f"CONTINUATION_{direction}")
    else:
        rev += 1

    loc_bonus = min(2, loc_score) // 2
    cont += loc_bonus

    total = cont + rev
    return {
        "continuation_score": cont,
        "reversal_score": rev,
        "total_evidence": total,
        "aligned_with_active": aligned,
        "reason_codes": reasons,
        **ctx,
    }


def evaluate_opportunity(
    m: MTFArrays,
    i: int,
    original_direction: str,
    cfg: dict,
    model: str = "D4",
    reversal_rule: str = "R1",
) -> dict:
    """Full two-sided evaluation at bar i (T0)."""
    active = active_move_at_bar(m, i, cfg)
    struct = structural_features(m, i, cfg)
    counter = countertrend_strength(m, i, active, cfg)

    loc_long, _ = location_score(m, i, "LONG", cfg)
    loc_short, _ = location_score(m, i, "SHORT", cfg)
    loc_score = max(loc_long, loc_short)

    long_sc = score_side("LONG", m, i, active, struct, counter, loc_long, cfg)
    short_sc = score_side("SHORT", m, i, active, struct, counter, loc_short, cfg)

    mkt_state, mkt_reasons = classify_market_state(
        original_direction, active, structure_context(struct, active, original_direction), counter
    )

    shadow, relation, pick_reasons = _pick_direction(
        original_direction, long_sc, short_sc, active, struct, counter, cfg, model, reversal_rule
    )

    ctx15 = ctx15_at_1m(m, i, cfg)
    return {
        "bar_i": i,
        "original_direction": original_direction,
        "shadow_direction_t0": shadow,
        "direction_relation": relation,
        "market_state": mkt_state,
        "location_score": loc_score,
        "long_continuation_score": long_sc["continuation_score"],
        "short_continuation_score": short_sc["continuation_score"],
        "long_reversal_score": long_sc["reversal_score"],
        "short_reversal_score": short_sc["reversal_score"],
        "long_total": long_sc["continuation_score"] + long_sc["reversal_score"],
        "short_total": short_sc["continuation_score"] + short_sc["reversal_score"],
        "long_evidence": long_sc["total_evidence"],
        "short_evidence": short_sc["total_evidence"],
        "countertrend_ratio": counter["countertrend_ratio"],
        "active_1m": active["active_1m"],
        "active_5m": active["active_5m"],
        "active_15m": active["active_15m"],
        "dominant_active": active["dominant_active"],
        "15m_state": ctx15["state"],
        "5m_state": active["active_5m"],
        "reason_codes": "|".join(pick_reasons + mkt_reasons),
        "market_state_reasons": "|".join(mkt_reasons),
    }


def evaluate_opportunity_t1(m: MTFArrays, i: int, original_direction: str, cfg: dict, **kw) -> dict:
    """T1 — one additional completed 1M bar."""
    i1 = min(i + 1, m.m1_n - 1)
    out = evaluate_opportunity(m, i1, original_direction, cfg, **kw)
    out["bar_i"] = i
    out["eval_bar_i"] = i1
    out["shadow_direction_t1"] = out.pop("shadow_direction_t0")
    return out


def _pick_direction(
    original: str,
    long_sc: dict,
    short_sc: dict,
    active: dict,
    struct: dict,
    counter: dict,
    cfg: dict,
    model: str,
    reversal_rule: str,
) -> tuple[str, str, list[str]]:
    reasons: list[str] = []

    if model == "D0":
        return original, "SAME", ["ORIGINAL_DIRECTION"]

    if model == "D1":
        dom = active["dominant_active"]
        if dom in ("STRONG_UP", "UP"):
            return "LONG", ("SAME" if original == "LONG" else "FLIPPED"), ["D1_ACTIVE_ALIGN"]
        if dom in ("STRONG_DOWN", "DOWN"):
            return "SHORT", ("SAME" if original == "SHORT" else "FLIPPED"), ["D1_ACTIVE_ALIGN"]
        return original, "SAME", ["D1_UNCERTAIN_KEEP_ORIGINAL"]

    edge = cfg.get("direction_edge_min", 2)
    uncertain_thr = cfg.get("uncertain_threshold", 1)

    if model == "D2":
        long_pick = long_sc["continuation_score"] + (1 if struct["bull_structure"] else 0)
        short_pick = short_sc["continuation_score"] + (1 if struct["bear_structure"] else 0)
    elif model == "D3":
        long_pick = long_sc["continuation_score"] + long_sc["reversal_score"]
        short_pick = short_sc["continuation_score"] + short_sc["reversal_score"]
        if counter["countertrend_ratio"] >= cfg.get("countertrend_ratio_pullback", 0.5):
            dom = active["dominant_active"]
            if dom in ("STRONG_UP", "UP"):
                long_pick += 1
                short_pick -= 1
            elif dom in ("STRONG_DOWN", "DOWN"):
                short_pick += 1
                long_pick -= 1
    else:  # D4
        long_pick = _d4_score(long_sc, reversal_rule, cfg, "LONG", active, struct, counter)
        short_pick = _d4_score(short_sc, reversal_rule, cfg, "SHORT", active, struct, counter)

    diff = long_pick - short_pick
    if abs(diff) < uncertain_thr:
        return "UNCERTAIN", "UNCERTAIN", ["DIRECTION_UNCERTAIN"]
    shadow = "LONG" if diff > 0 else "SHORT"
    if abs(diff) < edge:
        return "UNCERTAIN", "UNCERTAIN", ["EDGE_TOO_SMALL"]

    relation = "SAME" if shadow == original else "FLIPPED"
    if relation == "SAME":
        reasons.append("ORIGINAL_DIRECTION_SUPPORTED")
    else:
        reasons.append("ORIGINAL_DIRECTION_REJECTED")
    return shadow, relation, reasons


def _d4_score(side: dict, rule: str, cfg: dict, direction: str, active: dict, struct: dict, counter: dict) -> int:
    cont = side["continuation_score"]
    rev = side["reversal_score"]
    aligned = side["aligned_with_active"]

    if rule == "R0":
        return cont + rev
    if rule == "R1":
        extra = cfg.get("reversal_extra_r1", 2)
        if aligned:
            return cont + max(0, rev - extra)
        return cont + rev + extra
    # R2
    ctx = structure_context(struct, active, direction)
    if ctx["prior_weakening"] and ctx["opposite_strengthening"]:
        return cont + rev + 2
    if not aligned:
        return cont + max(0, rev - 1)
    return cont + rev
