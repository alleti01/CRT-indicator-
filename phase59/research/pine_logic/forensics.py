"""Phase58G — HIGH confidence band calibration forensics."""
from __future__ import annotations

import pandas as pd

from phase58b.research.simulation import metrics


def _code_flags(codes: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "active_aligned_code": codes.str.contains("CONF_ACTIVE_ALIGNED"),
        "active_opposed_code": codes.str.contains("CONF_ACTIVE_OPPOSED"),
        "struct_aligned_code": codes.str.contains("CONF_STRUCTURE_ALIGNED"),
        "struct_opposed_code": codes.str.contains("CONF_STRUCTURE_OPPOSED"),
        "htf_support_code": codes.str.contains("CONF_HTF_SUPPORT"),
        "htf_contra_code": codes.str.contains("CONF_HTF_CONTRADICTION"),
        "ct_weak_code": codes.str.contains("CONF_COUNTERTREND_WEAK"),
        "ct_strong_code": codes.str.contains("CONF_COUNTERTREND_STRONG"),
        "fr_high_code": codes.str.contains("FALSE_REVERSAL_HIGH"),
    })


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal feature flags used for HIGH forensics."""
    out = df.copy()
    flags = _code_flags(out["reason_codes"])
    for col in flags.columns:
        out[col] = flags[col].values

    out["missing_vh_confirm"] = (
        out["active_aligned_code"]
        & out["struct_aligned_code"]
        & ~out["htf_support_code"]
        & ~out["ct_weak_code"]
    )
    out["pullback_conflict"] = (out["market_state"] == "PULLBACK") & ~out["aligned_with_active"]
    out["htf_ltf_disagree"] = (
        ((out["original_direction"] == "LONG") & (out["15m_state"] == "BEARISH") & out["aligned_with_active"])
        | ((out["original_direction"] == "SHORT") & (out["15m_state"] == "BULLISH") & out["aligned_with_active"])
        | ((out["original_direction"] == "LONG") & (out["15m_state"] == "BULLISH") & ~out["aligned_with_active"])
        | ((out["original_direction"] == "SHORT") & (out["15m_state"] == "BEARISH") & ~out["aligned_with_active"])
    )
    out["weak_reversal_attempt"] = (
        ~out["aligned_with_active"]
        & out["reversal_support"].isin(["NONE", "WEAK"])
    )
    out["ambiguous_reaction"] = out["market_state"] == "UNCERTAIN"
    out["good_location"] = out["location_score"] >= 2

    out["high_subtype"] = out.apply(classify_high_subtype, axis=1)
    out["band_recal"] = out.apply(recalibrate_band, axis=1)
    out["feature_combo"] = out.apply(_feature_combo, axis=1)
    return out


def classify_high_subtype(row: pd.Series) -> str:
    """Split HIGH band into CLEAN / CONFLICTED / REVERSAL without delay."""
    if row.get("direction_confidence_band") != "HIGH":
        return ""

    rev_ok = row["reversal_support"] in ("MODERATE", "STRONG")
    if row["active_opposed_code"] and rev_ok:
        return "HIGH_REVERSAL"

    if row["missing_vh_confirm"]:
        return "HIGH_CONFLICTED"

    return "HIGH_CLEAN"


def recalibrate_band(row: pd.Series) -> str:
    """Shadow-only band relabel: demote incomplete active+struct HIGH to MEDIUM."""
    band = row["direction_confidence_band"]
    if band != "HIGH":
        return band
    if row["active_opposed_code"] and row["reversal_support"] in ("MODERATE", "STRONG"):
        return "HIGH"
    if row["missing_vh_confirm"]:
        return "MEDIUM"
    return band


def _feature_combo(row: pd.Series) -> str:
    act = "ACT_ALN" if row["active_aligned_code"] else "ACT_OPP"
    st = "STR_ALN" if row["struct_aligned_code"] else "STR_OPP"
    if row["htf_support_code"]:
        htf = "HTF+"
    elif row["htf_contra_code"]:
        htf = "HTF-"
    else:
        htf = "HTF0"
    mkt = str(row["market_state"])[:4]
    rev = str(row["reversal_support"])[:3]
    return f"{act}+{st}+{htf}+{mkt}+{rev}"


def band_table(df: pd.DataFrame, band_col: str = "direction_confidence_band") -> pd.DataFrame:
    rows = []
    for band in ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]:
        sub = df.loc[df[band_col] == band]
        if sub.empty:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({
            "band": band,
            "count": len(sub),
            "win_rate": m.get("WinRate", 0),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
        })
    return pd.DataFrame(rows)


def high_subtype_table(df: pd.DataFrame) -> pd.DataFrame:
    high = df.loc[df["direction_confidence_band"] == "HIGH"]
    rows = []
    for subtype in ["HIGH_CLEAN", "HIGH_REVERSAL", "HIGH_CONFLICTED"]:
        sub = high.loc[high["high_subtype"] == subtype]
        if sub.empty:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({
            "high_subtype": subtype,
            "count": len(sub),
            "pct_of_high": len(sub) / len(high) * 100 if len(high) else 0,
            "win_rate": m.get("WinRate", 0),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
        })
    return pd.DataFrame(rows)


def conflict_type_table(df: pd.DataFrame) -> pd.DataFrame:
    high = df.loc[df["direction_confidence_band"] == "HIGH"]
    dims = [
        ("trend_pullback_conflict", "pullback_conflict"),
        ("htf_ltf_disagreement", "htf_ltf_disagree"),
        ("htf_contradiction", "htf_contra_code"),
        ("weak_reversal_attempt", "weak_reversal_attempt"),
        ("ambiguous_reaction", "ambiguous_reaction"),
        ("false_reversal_high", high["false_reversal_risk"] == "HIGH"),
        ("active_opposed", ~high["aligned_with_active"]),
        ("active_aligned_missing_confirm", "missing_vh_confirm"),
        ("good_location", "good_location"),
        ("weak_location", ~high["location_score"].ge(2)),
    ]
    rows = []
    for label, mask in dims:
        if isinstance(mask, str):
            sub = high.loc[high[mask]]
        else:
            sub = high.loc[mask]
        if len(sub) < 20:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({
            "conflict_type": label,
            "count": len(sub),
            "pct_of_high": len(sub) / len(high) * 100,
            "AvgR": m.get("AvgR", 0),
            "TotalR": m.get("TotalR", 0),
            "win_rate": m.get("WinRate", 0),
        })
    return pd.DataFrame(rows).sort_values("count", ascending=False)


def combo_dominance(df: pd.DataFrame, min_count: int = 200) -> pd.DataFrame:
    high = df.loc[df["direction_confidence_band"] == "HIGH"]
    rows = []
    for combo, sub in high.groupby("feature_combo"):
        if len(sub) < min_count:
            continue
        m = metrics(sub["net_R"].values)
        rows.append({
            "feature_combo": combo,
            "count": len(sub),
            "high_subtype": sub["high_subtype"].mode().iloc[0],
            "AvgR": m.get("AvgR", 0),
            "TotalR": m.get("TotalR", 0),
            "win_rate": m.get("WinRate", 0),
        })
    return pd.DataFrame(rows).sort_values("count", ascending=False)


def shadow_abstention(df: pd.DataFrame, abstain_mask: pd.Series, label: str) -> dict:
    kept = df.loc[~abstain_mask]
    abst = df.loc[abstain_mask]
    mk = metrics(kept["net_R"].values)
    ab = metrics(abst["net_R"].values)
    winners = df.loc[df["net_R"] > 0]
    losers = df.loc[df["net_R"] <= 0]
    wr = len(kept.loc[kept["net_R"] > 0]) / len(winners) * 100 if len(winners) else 0
    lr = len(abst.loc[abst["net_R"] <= 0]) / len(losers) * 100 if len(losers) else 0
    neg_avoided = abs(abst.loc[abst["net_R"] <= 0, "net_R"].sum()) if not abst.empty else 0
    pos_destroyed = abst.loc[abst["net_R"] > 0, "net_R"].sum() if not abst.empty else 0
    sel = neg_avoided / pos_destroyed if pos_destroyed > 0 else float("inf") if neg_avoided > 0 else 0
    return {
        "policy": label,
        "abstained": len(abst),
        "abstained_AvgR": ab.get("AvgR", 0),
        "abstained_TotalR": ab.get("TotalR", 0),
        "kept_AvgR": mk.get("AvgR", 0),
        "kept_TotalR": mk.get("TotalR", 0),
        "winners_retained_pct": wr,
        "losers_removed_pct": lr,
        "selectivity_ratio": sel,
    }


def check_monotonicity(band_df: pd.DataFrame) -> bool:
    order = ["VERY_HIGH", "HIGH", "MEDIUM", "LOW", "VERY_LOW"]
    avgs = []
    for band in order:
        row = band_df.loc[band_df["band"] == band]
        if not row.empty:
            avgs.append(float(row["AvgR"].iloc[0]))
    if len(avgs) < 2:
        return True
    return all(avgs[i] >= avgs[i + 1] for i in range(len(avgs) - 1))


def score_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    high = df.loc[df["direction_confidence_band"] == "HIGH"]
    rows = []
    for score in sorted(high["direction_confidence_score"].unique()):
        sub = high.loc[high["direction_confidence_score"] == score]
        m = metrics(sub["net_R"].values)
        rows.append({
            "score": int(score),
            "count": len(sub),
            "AvgR": m.get("AvgR", 0),
            "TotalR": m.get("TotalR", 0),
            "win_rate": m.get("WinRate", 0),
        })
    return pd.DataFrame(rows)
