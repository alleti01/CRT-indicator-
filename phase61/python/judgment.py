"""Phase61 — causal judgment features and hypothesis testing."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.context import compute_context
from phase58.research.location import compute_location
from phase58.research.reaction import compute_all_reactions
from phase58b.research.simulation import metrics
from phase60.python.context_maps import ctx15_at_1m, ctx5_at_1m, loc5_at_1m
from phase60.python.pipeline import phase60_htf_context


def enrich_causal_features(signals: pd.DataFrame, m_market, m_mtf, cfg: dict, sample: int | None = None) -> pd.DataFrame:
    """Add causal decision-time features at signal_i."""
    sub = signals if sample is None else signals.sample(min(sample, len(signals)), random_state=61)
    rows = []
    with phase60_htf_context():
        for _, r in sub.iterrows():
            i = int(r["signal_i"])
            direction = r["direction"]
            ctx = compute_context(m_market, i)
            loc = compute_location(m_market, i, direction)
            react = compute_all_reactions(m_market, i, direction, cfg)
            c15 = ctx15_at_1m(m_mtf, i, cfg)
            c5 = ctx5_at_1m(m_mtf, i, cfg)
            loc5 = loc5_at_1m(m_mtf, i, direction, cfg)
            chase = abs(float(r["entry_price"]) - float(r.get("opp_created_price", r["entry_price"]))) / float(r["atr"])
            rows.append(
                {
                    "signal_i": i,
                    "location_score": loc["score"] + loc5["score"],
                    "reaction_score": react["score"],
                    "context_confidence": ctx["confidence"],
                    "m5_state": c5.get("direction", "NEUTRAL"),
                    "m15_state": c15.get("state", "NEUTRAL"),
                    "chase_atr": chase,
                    "is_first_signal": bool(r.get("is_first", r.get("opp_rank", 1) == 1)),
                    "extension_atr": abs(float(m_market.cl[i]) - float(m_market.lo[max(0, i - 20)])) / float(r["atr"])
                    if direction == "LONG"
                    else abs(float(m_market.hi[max(0, i - 20)]) - float(m_market.cl[i])) / float(r["atr"]),
                }
            )
    return sub.merge(pd.DataFrame(rows), on="signal_i", how="left")


def label_good_bad(df: pd.DataFrame) -> pd.DataFrame:
    """Retrospective labels for analysis only."""
    out = df.copy()
    good = (out["mfe_60m_atr"] >= 2.0) & (out["mae_60m_atr"] < 1.25)
    bad = (out["final_ret_60m_atr"] < -0.5) | ((out["mfe_60m_atr"] < 0.5) & (out["mae_60m_atr"] > 1.0))
    out["research_good"] = good
    out["research_bad"] = bad
    return out


def test_hypothesis(df: pd.DataFrame, name: str, take_mask: pd.Series) -> dict:
    """Filter damage metric for a judgment rule."""
    good = df["research_good"]
    bad = df["research_bad"]
    take = take_mask
    good_removed = good & ~take
    bad_removed = bad & ~take
    good_kept = good & take
    bad_kept = bad & take
    gr = good_removed.sum()
    br = bad_removed.sum()
    selectivity = br / gr if gr > 0 else float("inf")
    baseline_r = df.loc[take, "final_ret_60m_atr"].mean() if take.any() else 0
    all_r = df["final_ret_60m_atr"].mean()
    large = df["reached_plus_2.0atr"] if "reached_plus_2.0atr" in df.columns else df["mfe_60m_atr"] >= 2
    return {
        "name": name,
        "take_count": int(take.sum()),
        "pass_count": int((~take).sum()),
        "bad_removed": int(br),
        "good_removed": int(gr),
        "selectivity_ratio": float(selectivity),
        "winner_retention": float(good_kept.sum() / max(1, good.sum())),
        "large_move_retention": float((take & large).sum() / max(1, large.sum())),
        "avg_r_change": float(baseline_r - all_r),
    }


def _first_mask(df: pd.DataFrame) -> pd.Series:
    if "is_first" in df.columns:
        return df["is_first"] == True
    if "is_first_signal" in df.columns:
        return df["is_first_signal"] == True
    if "opp_rank" in df.columns:
        return df["opp_rank"] == 1
    return pd.Series(True, index=df.index)


def build_hypotheses(df: pd.DataFrame) -> list[dict]:
    first = _first_mask(df)
    hyps = [
        ("H1_not_chased", df["chase_atr"] < 1.0),
        ("H2_reaction_quality", df["reaction_score"] >= 1),
        ("H3_no_htf_conflict", ~(
            ((df["direction"] == "LONG") & (df["m5_state"] == "BEARISH") & (df["m15_state"] == "BEARISH"))
            | ((df["direction"] == "SHORT") & (df["m5_state"] == "BULLISH") & (df["m15_state"] == "BULLISH"))
        )),
        ("H4_location_quality", df["location_score"] >= 1),
        ("H5_first_signal_only", first),
    ]
    return [test_hypothesis(df, n, m) for n, m in hyps]


def simple_scorecard(df: pd.DataFrame) -> pd.DataFrame:
    """Simple evidence scorecard derived from Task 10 patterns."""
    score = np.zeros(len(df))
    score += (df["location_score"] >= 1).astype(int)
    score += (df["reaction_score"] >= 1).astype(int)
    m5_ok = ((df["direction"] == "LONG") & (df["m5_state"].isin(["BULLISH", "NEUTRAL"]))) | (
        (df["direction"] == "SHORT") & (df["m5_state"].isin(["BEARISH", "NEUTRAL"]))
    )
    score += m5_ok.astype(int)
    score += (df["chase_atr"] < 1.0).astype(int)
    conflict = (
        ((df["direction"] == "LONG") & (df["m5_state"] == "BEARISH") & (df["m15_state"] == "BEARISH"))
        | ((df["direction"] == "SHORT") & (df["m5_state"] == "BULLISH") & (df["m15_state"] == "BULLISH"))
    )
    score -= conflict.astype(int)
    score -= (df["extension_atr"] > 2.0).astype(int)
    out = df.copy()
    out["judgment_score"] = score
    out["judgment"] = "PASS"
    out.loc[out["judgment_score"] >= 3, "judgment"] = "TAKE"
    out.loc[(out["judgment_score"] == 2) & _first_mask(out), "judgment"] = "WAIT"
    return out
