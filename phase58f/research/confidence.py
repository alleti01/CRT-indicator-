"""Direction confidence engine — supports ORIGINAL Phase58D direction only."""
from __future__ import annotations

from phase58b.research.precompute import MTFArrays
from phase58d.research.context_maps import ctx15_at_1m, ctx5_at_1m, location_score
from phase58e.research.active_move import active_move_at_bar, side_aligned_with_active, _score_state
from phase58e.research.market_state import classify_market_state
from phase58e.research.structure import countertrend_strength, structural_features, structure_context


def false_reversal_risk(
    original_dir: str,
    active: dict,
    counter: dict,
    ctx: dict,
    aligned: bool,
    cfg: dict,
    market_state: str = "UNCERTAIN",
) -> tuple[str, list[str]]:
    """HIGH when countertrend vs dominant move with weak reversal evidence."""
    reasons: list[str] = []
    ct = counter.get("countertrend_ratio", 0.0)
    pull = cfg.get("countertrend_ratio_pullback", 0.5)

    if aligned:
        return "LOW", ["FALSE_REVERSAL_LOW"]

    dom = active["dominant_active"]
    dom_bull = dom in ("STRONG_UP", "UP")
    dom_bear = dom in ("STRONG_DOWN", "DOWN")
    opposed = (original_dir == "SHORT" and dom_bull) or (original_dir == "LONG" and dom_bear)

    weak_rev = not ctx.get("prior_weakening") and not ctx.get("opposite_strengthening")

    if opposed and ct < pull and weak_rev:
        reasons.extend(["ACTIVE_MOVE_OPPOSED", "COUNTERTREND_WEAK", "NO_CONTROL_TRANSFER"])
        return "HIGH", reasons

    if market_state == "PULLBACK" and opposed and ct < cfg.get("countertrend_ratio_reversal", 0.85):
        reasons.extend(["PULLBACK_AGAINST_DOMINANT", "WEAK_REVERSAL_SUPPORT"])
        return "HIGH", reasons

    if not aligned and ct < pull:
        reasons.append("COUNTERTREND_WEAK")
        return "MEDIUM", reasons
    return "LOW", reasons


def reversal_support(ctx: dict, counter: dict, struct: dict, original_dir: str, cfg: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    ct = counter.get("countertrend_ratio", 0.0)
    rev_thr = cfg.get("countertrend_ratio_reversal", 0.85)

    score = 0
    if ctx.get("prior_weakening"):
        score += 1
        reasons.append("PRIOR_MOVE_WEAKENING")
    if ctx.get("opposite_strengthening"):
        score += 1
        reasons.append("OPPOSITE_STRENGTHENING")
    if ct >= rev_thr:
        score += 2
        reasons.append("COUNTERTREND_STRONG")
    elif ct >= cfg.get("countertrend_ratio_pullback", 0.5):
        score += 1

    if original_dir == "LONG" and struct.get("failed_up_extension"):
        score += 1
        reasons.append("FAILED_UP_EXTENSION")
    if original_dir == "SHORT" and struct.get("failed_down_extension"):
        score += 1
        reasons.append("FAILED_DOWN_EXTENSION")

    if score >= 3:
        return "STRONG", reasons
    if score >= 2:
        return "MODERATE", reasons
    if score >= 1:
        return "WEAK", reasons
    return "NONE", reasons


def compute_confidence(m: MTFArrays, i: int, original_dir: str, cfg: dict) -> dict:
    """Causal confidence for the original Phase58D direction at bar i."""
    active = active_move_at_bar(m, i, cfg)
    struct = structural_features(m, i, cfg)
    counter = countertrend_strength(m, i, active, cfg)
    ctx = structure_context(struct, active, original_dir)
    ctx15 = ctx15_at_1m(m, i, cfg)
    ctx5 = ctx5_at_1m(m, i, cfg)
    aligned = side_aligned_with_active(original_dir, active)
    loc_sc, _ = location_score(m, i, original_dir, cfg)

    score = 0
    reasons: list[str] = []
    dom_sc = _score_state(active["dominant_active"])

    if original_dir == "LONG":
        if dom_sc >= 1:
            score += 2
            reasons.append("CONF_ACTIVE_ALIGNED")
        elif dom_sc <= -1:
            score -= 2
            reasons.append("CONF_ACTIVE_OPPOSED")
    else:
        if dom_sc <= -1:
            score += 2
            reasons.append("CONF_ACTIVE_ALIGNED")
        elif dom_sc >= 1:
            score -= 2
            reasons.append("CONF_ACTIVE_OPPOSED")

    if ctx["structure_intact"]:
        score += 1
        reasons.append("CONF_STRUCTURE_ALIGNED")
    else:
        score -= 1
        reasons.append("CONF_STRUCTURE_OPPOSED")

    if original_dir == "LONG":
        if ctx15["state"] == "BULLISH":
            score += 1
            reasons.append("CONF_HTF_SUPPORT")
        elif ctx15["state"] == "BEARISH" and ctx15["strength"] <= -1:
            score -= 1
            reasons.append("CONF_HTF_CONTRADICTION")
    else:
        if ctx15["state"] == "BEARISH":
            score += 1
            reasons.append("CONF_HTF_SUPPORT")
        elif ctx15["state"] == "BULLISH" and ctx15["strength"] >= 1:
            score -= 1
            reasons.append("CONF_HTF_CONTRADICTION")

    ct = counter.get("countertrend_ratio", 0.0)
    if ct < cfg.get("countertrend_ratio_pullback", 0.5):
        if aligned:
            score += 1
            reasons.append("CONF_COUNTERTREND_WEAK")
    elif ct >= cfg.get("countertrend_ratio_reversal", 0.85):
        if not aligned:
            score += 1
            reasons.append("CONF_COUNTERTREND_STRONG")

    mkt_state, mkt_r = classify_market_state(original_dir, active, ctx, counter)
    fr_risk, fr_reasons = false_reversal_risk(
        original_dir, active, counter, ctx, aligned, cfg, market_state=mkt_state,
    )
    rev_sup, rev_reasons = reversal_support(ctx, counter, struct, original_dir, cfg)

    if fr_risk == "HIGH":
        score -= 2
        reasons.append("FALSE_REVERSAL_HIGH")
    elif fr_risk == "MEDIUM":
        score -= 1

    if rev_sup in ("STRONG", "MODERATE") and not aligned:
        score += 1 if rev_sup == "MODERATE" else 2
        reasons.append(f"CONF_REVERSAL_SUPPORT_{rev_sup}")

    reasons.extend(mkt_r)
    band = _confidence_band(score, cfg)

    return {
        "bar_i": i,
        "original_direction": original_dir,
        "direction_confidence_score": score,
        "direction_confidence_band": band,
        "original_dir_support_score": score,
        "false_reversal_risk": fr_risk,
        "reversal_support": rev_sup,
        "market_state": mkt_state,
        "location_score": loc_sc,
        "active_1m": active["active_1m"],
        "active_5m": active["active_5m"],
        "active_15m": active["active_15m"],
        "dominant_active": active["dominant_active"],
        "15m_state": ctx15["state"],
        "5m_state": ctx5.get("direction", "NEUTRAL"),
        "countertrend_ratio": ct,
        "aligned_with_active": aligned,
        "reason_codes": "|".join(reasons + fr_reasons + rev_reasons),
    }


def _confidence_band(score: int, cfg: dict) -> str:
    if score >= cfg.get("confidence_very_high", 4):
        return "VERY_HIGH"
    if score >= cfg.get("confidence_high", 2):
        return "HIGH"
    if score >= cfg.get("confidence_medium", 0):
        return "MEDIUM"
    if score >= cfg.get("confidence_low", -2):
        return "LOW"
    return "VERY_LOW"


def opposite_confidence_for_rare_flip(m: MTFArrays, i: int, original_dir: str, cfg: dict) -> dict:
    """Shadow-only: confidence for opposite side (never used for primary decision)."""
    opp = "SHORT" if original_dir == "LONG" else "LONG"
    return compute_confidence(m, i, opp, cfg)
