"""Phase58H analysis and reporting."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics
from phase58h.research.filters import apply_h_model


def model_metrics(
    df: pd.DataFrame,
    model: str,
    baseline_decisions: pd.Series | None = None,
    meaningful_col: str | None = None,
    real_reversal_col: str | None = None,
) -> dict:
    decisions = apply_h_model(df, model)
    kept = df.loc[decisions == "KEEP"]
    abst = df.loc[decisions == "ABSTAIN"]

    mk = metrics(kept["net_R"].values) if not kept.empty else dict(N=0, AvgR=0, PF=0, TotalR=0, MaxDD=0, WinRate=0)
    ab = metrics(abst["net_R"].values) if not abst.empty else dict(N=0, AvgR=0, PF=0, TotalR=0)

    winners = df.loc[df["net_R"] > 0]
    losers = df.loc[df["net_R"] <= 0]
    wr = len(kept.loc[kept["net_R"] > 0]) / len(winners) * 100 if len(winners) else 0
    lr = len(abst.loc[abst["net_R"] <= 0]) / len(losers) * 100 if len(losers) else 0

    neg_avoided = abs(abst.loc[abst["net_R"] <= 0, "net_R"].sum()) if not abst.empty else 0
    pos_destroyed = abst.loc[abst["net_R"] > 0, "net_R"].sum() if not abst.empty else 0
    sel = neg_avoided / pos_destroyed if pos_destroyed > 0 else float("inf") if neg_avoided > 0 else 0

    new_abst = abst
    if baseline_decisions is not None:
        new_mask = (decisions == "ABSTAIN") & (baseline_decisions == "KEEP")
        new_abst = df.loc[new_mask]

    mm_ret = rr_ret = np.nan
    if meaningful_col and meaningful_col in df.columns:
        mm = df.loc[df[meaningful_col].fillna(False)]
        if len(mm):
            mm_ret = len(kept.loc[kept.index.isin(mm.index)]) / len(mm) * 100
    if real_reversal_col and real_reversal_col in df.columns:
        rr = df.loc[df[real_reversal_col].fillna(False)]
        if len(rr):
            rr_ret = len(kept.loc[kept.index.isin(rr.index)]) / len(rr) * 100

    return {
        "model": model,
        "trades_retained": mk.get("N", 0),
        "trades_abstained": len(abst),
        "new_abstains_vs_p4": len(new_abst),
        "AvgR": mk.get("AvgR", 0),
        "PF": mk.get("PF", 0),
        "TotalR": mk.get("TotalR", 0),
        "MaxDD": mk.get("MaxDD", 0),
        "WinRate": mk.get("WinRate", 0),
        "winners_retained_pct": wr,
        "losers_removed_pct": lr,
        "meaningful_move_retention_pct": mm_ret,
        "real_reversal_retention_pct": rr_ret,
        "negative_R_avoided": neg_avoided,
        "positive_R_destroyed": pos_destroyed,
        "selectivity_ratio": sel,
        "median_delay": 0,
        "max_delay": 0,
        "marginal_abstained_AvgR": metrics(new_abst["net_R"].values).get("AvgR", 0) if not new_abst.empty else 0,
        "marginal_abstained_n": len(new_abst),
    }


def incremental_vs_p4(h_row: dict, p4_row: dict) -> dict:
    return {
        "model": h_row["model"],
        "incremental_total_r_vs_p4": h_row["TotalR"] - p4_row["TotalR"],
        "incremental_negative_r_avoided": h_row["negative_R_avoided"] - p4_row["negative_R_avoided"],
        "incremental_positive_r_destroyed": h_row["positive_R_destroyed"] - p4_row["positive_R_destroyed"],
        "new_abstains_vs_p4": h_row["new_abstains_vs_p4"],
    }


def funnel_row(df: pd.DataFrame, label: str, mask: pd.Series) -> dict:
    sub = df.loc[mask]
    if sub.empty:
        return {"funnel_step": label, "trades": 0}
    m = metrics(sub["net_R"].values)
    winners = sub.loc[sub["net_R"] > 0]
    losers = sub.loc[sub["net_R"] <= 0]
    rr = sub.loc[sub.get("real_reversal", False)] if "real_reversal" in sub.columns else pd.DataFrame()
    mm = sub.loc[sub.get("meaningful_move", False)] if "meaningful_move" in sub.columns else pd.DataFrame()
    return {
        "funnel_step": label,
        "trades": len(sub),
        "AvgR": m.get("AvgR", 0),
        "PF": m.get("PF", 0),
        "TotalR": m.get("TotalR", 0),
        "win_rate": m.get("WinRate", 0),
        "negative_R": sub.loc[sub["net_R"] <= 0, "net_R"].sum(),
        "positive_R": sub.loc[sub["net_R"] > 0, "net_R"].sum(),
        "winner_pct": len(winners) / len(sub) * 100 if len(sub) else 0,
        "loser_pct": len(losers) / len(sub) * 100 if len(sub) else 0,
        "meaningful_moves": len(mm),
        "real_reversals": len(rr),
    }


def build_funnel(df: pd.DataFrame) -> pd.DataFrame:
    hc = df["high_subtype"] == "HIGH_CONFLICTED"
    rows = [
        funnel_row(df, "HIGH_CONFLICTED", hc),
        funnel_row(df, "HC + HTF_CONTRA", hc & df["htf_contra_code"]),
        funnel_row(df, "HC + HTF_CONTRA + WEAK_REV", hc & df["htf_contra_code"] & df["reversal_support"].isin(["NONE", "WEAK"])),
        funnel_row(
            df,
            "HC + HTF_CONTRA + WEAK_REV + NON_GOOD_LOC",
            hc & df["htf_contra_code"] & df["reversal_support"].isin(["NONE", "WEAK"]) & ~df["good_location"],
        ),
        funnel_row(
            df,
            "HC + HTF_CONTRA + WEAK_REV + STRONG_ACTIVE_OPPOSITION",
            hc & df["htf_contra_code"] & df["reversal_support"].isin(["NONE", "WEAK"])
            & (
                ((df["original_direction"] == "LONG") & (df["dominant_active"] == "STRONG_DOWN"))
                | ((df["original_direction"] == "SHORT") & (df["dominant_active"] == "STRONG_UP"))
            ),
        ),
    ]
    return pd.DataFrame(rows)


def direction_pool_impact(df: pd.DataFrame, decisions: pd.Series, loc_thr: int = 2) -> tuple[dict, dict]:
    """Evaluation-only good/bad direction pool impact."""
    t = df.copy()
    t["decision"] = decisions.values
    t["loc_good"] = t["location_score"] >= loc_thr
    t["dir_good"] = t["net_R"] > 0

    good_pool = t.loc[t["loc_good"] & t["dir_good"]]
    bad_pool = t.loc[t["loc_good"] & ~t["dir_good"]]
    abst = t.loc[t["decision"] == "ABSTAIN"]

    good_abst = abst.loc[abst.index.isin(good_pool.index)]
    bad_abst = abst.loc[abst.index.isin(bad_pool.index)]

    good = {
        "good_direction_trades_removed": len(good_abst),
        "good_direction_winners_removed": len(good_abst.loc[good_abst["net_R"] > 0]),
        "good_direction_r_destroyed": good_abst.loc[good_abst["net_R"] > 0, "net_R"].sum(),
    }
    bad = {
        "bad_direction_trades_removed": len(bad_abst),
        "bad_direction_losses_removed": len(bad_abst.loc[bad_abst["net_R"] <= 0]),
        "bad_direction_negative_r_avoided": abs(bad_abst.loc[bad_abst["net_R"] <= 0, "net_R"].sum()),
    }
    return good, bad


def p4_overlap(df: pd.DataFrame, h_decisions: pd.Series, model: str) -> dict:
    p4 = apply_h_model(df, "H0")
    p4_only = (p4 == "ABSTAIN") & (h_decisions == "KEEP")
    h_only = (p4 == "KEEP") & (h_decisions == "ABSTAIN")
    both = (p4 == "ABSTAIN") & (h_decisions == "ABSTAIN")
    return {"model": model, "p4_only": int(p4_only.sum()), "h_only": int(h_only.sum()), "p4_and_h": int(both.sum())}


def bootstrap_ci(values: np.ndarray, n_boot: int = 500, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    vals = values[~np.isnan(values)]
    if len(vals) < 10:
        return (np.nan, np.nan)
    boots = []
    for _ in range(n_boot):
        samp = rng.choice(vals, size=len(vals), replace=True)
        boots.append(float(np.mean(samp)))
    lo = float(np.quantile(boots, alpha / 2))
    hi = float(np.quantile(boots, 1 - alpha / 2))
    return lo, hi


def select_candidate(train_rows: list[dict]) -> str | None:
    """Pick simplest model passing train guardrails."""
    order = ["H1", "H2", "H3", "H4"]
    passing = []
    for m in order:
        row = next((r for r in train_rows if r["model"] == m), None)
        if not row:
            continue
        if row["marginal_abstained_n"] < 30:
            continue
        if row["incremental_total_r_vs_p4"] <= 0:
            continue
        if row["selectivity_ratio"] <= 1.5:
            continue
        if row["winners_retained_pct"] <= 97:
            continue
        mm = row.get("meaningful_move_retention_pct", 100)
        rr = row.get("real_reversal_retention_pct", 100)
        if mm < 95 or rr < 95:
            continue
        passing.append(m)
    return passing[0] if passing else None
