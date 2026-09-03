"""Phase58E analysis outputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics


def model_comparison(systems: dict[str, pd.DataFrame], audit: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, trades in systems.items():
        if trades.empty:
            rows.append({"model": name, "trades": 0})
            continue
        m = metrics(trades["net_R"].values)
        rel = audit.set_index("opportunity_id") if "opportunity_id" in audit.columns else audit
        flipped = int((trades.get("flipped", pd.Series(False, index=trades.index))).sum()) if "flipped" in trades.columns else 0
        rows.append({
            "model": name,
            "trades": m.get("N", 0),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
            "MaxDD": m.get("MaxDD", 0),
            "WinRate": m.get("WinRate", 0),
            "flipped_directions": flipped,
        })
    return pd.DataFrame(rows)


def location_direction_matrix(audit: pd.DataFrame, trades: pd.DataFrame, loc_thr: int = 2) -> pd.DataFrame:
    m = trades.merge(
        audit[["opportunity_id", "location_score", "shadow_direction_t0", "direction_relation"]],
        on="opportunity_id", how="inner", suffixes=("_trade", "_audit"),
    )
    loc_col = "location_score_audit" if "location_score_audit" in m.columns else "location_score"
    m["loc_good"] = m[loc_col] >= loc_thr
    m["dir_good"] = m["net_R"] > 0
    rows = []
    for loc_label, loc_val in [("LOCATION_GOOD", True), ("LOCATION_BAD", False)]:
        for dir_label, dir_val in [("DIRECTION_GOOD", True), ("DIRECTION_BAD", False)]:
            sub = m.loc[(m["loc_good"] == loc_val) & (m["dir_good"] == dir_val)]
            met = metrics(sub["net_R"].values) if not sub.empty else {}
            rows.append({
                "location": loc_label if loc_val else "LOCATION_BAD",
                "direction": dir_label if dir_val else "DIRECTION_BAD",
                "count": len(sub),
                "AvgR": met.get("AvgR", 0),
                "PF": met.get("PF", 0),
                "TotalR": met.get("TotalR", 0),
            })
    return pd.DataFrame(rows)


def false_reversal_analysis(audit: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Phase58D trades against dominant move with weak reversal evidence."""
    m = trades.merge(audit, on="opportunity_id")
    false_rev = m.loc[
        (m["market_state"] == "PULLBACK") & (m["direction_relation"] == "SAME") & (m["net_R"] <= 0)
    ]
    met = metrics(false_rev["net_R"].values) if not false_rev.empty else {}
    return pd.DataFrame([{
        "false_reversal_count": len(false_rev),
        "AvgR": met.get("AvgR", 0),
        "PF": met.get("PF", 0),
        "TotalR": met.get("TotalR", 0),
        "win_rate": met.get("WinRate", 0),
    }])


def continuation_pullback_tables(audit: pd.DataFrame, trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    m = trades.merge(audit[["opportunity_id", "market_state", "shadow_direction_t0", "direction_relation"]], on="opportunity_id")
    cont_rows, pull_rows = [], []
    for state, rows in m.groupby("market_state"):
        met = metrics(rows["net_R"].values)
        row = {"market_state": state, "count": len(rows), **met, "win_rate": met.get("WinRate", 0)}
        if state == "CONTINUATION":
            cont_rows.append(row)
        elif state == "PULLBACK":
            pull_rows.append(row)
        else:
            cont_rows.append(row)
    return pd.DataFrame(cont_rows), pd.DataFrame(pull_rows if pull_rows else cont_rows)


def flip_economics(cats: pd.DataFrame, flip_sim: pd.DataFrame) -> pd.DataFrame:
    correct = int((cats["category"] == "FLIP_CORRECT").sum()) if not cats.empty else 0
    wrong = int((cats["category"] == "FLIP_WRONG").sum()) if not cats.empty else 0
    delta = float(flip_sim["flip_delta_R"].sum()) if not flip_sim.empty and "flip_delta_R" in flip_sim.columns and flip_sim["flip_delta_R"].notna().any() else 0.0
    if delta == 0 and not flip_sim.empty and "original_net_R" in flip_sim.columns:
        delta = float((flip_sim["net_R"] - flip_sim["original_net_R"]).sum())
    return pd.DataFrame([
        {"metric": "flip_count", "value": correct + wrong},
        {"metric": "correct_flips", "value": correct},
        {"metric": "incorrect_flips", "value": wrong},
        {"metric": "flip_totalR_delta", "value": delta},
        {"metric": "original_losers_corrected", "value": int(((cats["category"] == "FLIP_CORRECT") & (cats["original_net_R"] <= 0)).sum()) if not cats.empty else 0},
        {"metric": "original_winners_destroyed", "value": int(((cats["category"] == "FLIP_WRONG") & (cats["original_net_R"] > 0)).sum()) if not cats.empty else 0},
    ])


def htf_alignment_table(audit: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    m = trades.merge(audit, on="opportunity_id")
    rows = []
    for _, r in m.head(50000).iterrows():
        g = _alignment_group(r)
        rows.append({"group": g, "original_direction": r["direction"], "shadow_t0": r.get("shadow_direction_t0", ""), "net_R": r["net_R"]})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.groupby("group").agg(
        count=("net_R", "count"), AvgR=("net_R", "mean"), TotalR=("net_R", "sum")
    ).reset_index()


def _alignment_group(r) -> str:
    a15 = r.get("active_15m", "NEUTRAL")
    a5 = r.get("active_5m", "NEUTRAL")
    a1 = r.get("active_1m", "NEUTRAL")
    if a15 == a5 == a1:
        return "ALL_ALIGNED"
    if a15 == a5:
        return "15M_5M_ALIGNED_1M_COUNTER"
    if a5 == a1:
        return "5M_1M_ALIGNED"
    return "MIXED"


def year_stability(trades: pd.DataFrame, idx) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = [idx[int(i)].year for i in t["entry_i"]]
    rows = []
    for yr, g in t.groupby("year"):
        m = metrics(g["net_R"].values)
        flips = int(g["flipped"].sum()) if "flipped" in g.columns else 0
        rows.append({"year": yr, "trades": len(g), "flips": flips, **m})
    return pd.DataFrame(rows)
