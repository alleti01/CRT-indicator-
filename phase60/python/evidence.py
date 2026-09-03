"""Phase60 evidence wrapper — strong_contradiction uses 1M index i."""
from __future__ import annotations

from phase58.research.reaction import compute_all_reactions
from phase58b.research.context_15m import score_15m_for_direction
from phase58b.research.precompute import MTFArrays
from phase60.python.context_maps import (
    ctx15_at_1m,
    ctx5_at_1m,
    loc5_at_1m,
    location_score,
    m1_market_view,
    strong_contradiction,
)


def compute_evidence(m: MTFArrays, i: int, direction: str, cfg: dict) -> dict:
    ctx15 = ctx15_at_1m(m, i, cfg)
    ctx5 = ctx5_at_1m(m, i, cfg)
    loc5 = loc5_at_1m(m, i, direction, cfg)
    loc_sc, loc_reasons = location_score(m, i, direction, cfg)
    c15, r15 = score_15m_for_direction(ctx15, direction)

    if direction == "LONG":
        dir5 = min(2, int(ctx5.get("bull", 0)))
    else:
        dir5 = min(2, int(ctx5.get("bear", 0)))
    direction_score = c15 + dir5
    dir_reasons = r15 + ctx5.get("reasons", [])

    m1 = m1_market_view(m, cfg.get("swing_period", 5))
    react = compute_all_reactions(m1, i, direction, cfg)
    reaction_score = react["score"]

    contra = 0
    contra_reasons: list[str] = []
    if direction == "LONG" and ctx15["state"] == "BEARISH" and ctx15["strength"] <= -1:
        contra -= 1
        contra_reasons.append("HTF_CONTRADICTION")
    elif direction == "SHORT" and ctx15["state"] == "BULLISH" and ctx15["strength"] >= 1:
        contra -= 1
        contra_reasons.append("HTF_CONTRADICTION")

    if direction == "LONG" and ctx5.get("direction") == "BEARISH" and ctx5.get("bear", 0) >= 2:
        contra -= 1
        contra_reasons.append("5M_EXPANSION_AGAINST")
    elif direction == "SHORT" and ctx5.get("direction") == "BULLISH" and ctx5.get("bull", 0) >= 2:
        contra -= 1
        contra_reasons.append("5M_EXPANSION_AGAINST")

    strong, sr = strong_contradiction(ctx15, direction, m, i)
    if strong and cfg.get("hard_filter_enabled", False):
        contra -= cfg.get("strong_contra_penalty", 3)
        contra_reasons.extend(sr)

    total = loc_sc + direction_score + reaction_score + contra
    return {
        "location_score": loc_sc,
        "direction_score": direction_score,
        "reaction_score": reaction_score,
        "contradiction": contra,
        "total_evidence": total,
        "15m_state": ctx15["state"],
        "15m_strength": ctx15["strength"],
        "5m_state": ctx5.get("direction", "NEUTRAL"),
        "5m_location_score": loc5["score"],
        "strong_contradiction": strong,
        "reason_codes": loc_reasons + dir_reasons + react["reasons"] + contra_reasons,
    }
