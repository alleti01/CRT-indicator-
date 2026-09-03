"""Post-stop MFE and outcome transition audits."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58j.research.independent_simulator import entry_atr, init_levels


def post_stop_mfe(
    hi: np.ndarray,
    lo: np.ndarray,
    entry_i: int,
    exit_i: int,
    direction: str,
    entry_price: float,
    risk_pts: float,
    horizon: int,
) -> float:
    sign = 1 if direction == "LONG" else -1
    end = min(len(hi) - 1, exit_i + horizon)
    best = 0.0
    for i in range(exit_i + 1, end + 1):
        if direction == "LONG":
            best = max(best, (hi[i] - entry_price) / risk_pts)
        else:
            best = max(best, (entry_price - lo[i]) / risk_pts)
    return best


def outcome_transition(m0: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    m = m0.merge(m1, on="trade_id", suffixes=("_m0", "_m1"))
    rows = []
    for _, r in m.iterrows():
        k = f"{r['exit_reason_m0']}_TO_{r['exit_reason_m1']}"
        if r["exit_reason_m0"] == "STOP" and r["exit_reason_m1"] == "TARGET":
            k = "M0_STOP_M1_TARGET"
        elif r["exit_reason_m0"] == r["exit_reason_m1"]:
            k = "SAME_RESULT"
        rows.append({
            "trade_id": r["trade_id"],
            "transition": k,
            "m0_r": r["net_R_m0"],
            "m1_r": r["net_R_m1"],
            "delta_r": r["net_R_m1"] - r["net_R_m0"],
        })
    df = pd.DataFrame(rows)
    agg = df.groupby("transition").agg(
        N=("trade_id", "count"),
        m0_total_r=("m0_r", "sum"),
        m1_total_r=("m1_r", "sum"),
        delta_r=("delta_r", "sum"),
    ).reset_index()
    total_delta = df["delta_r"].sum()
    agg["pct_of_improvement"] = agg["delta_r"] / total_delta * 100 if total_delta else 0
    return agg, df


def target_stop_decomposition(m0: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    m = m0.merge(m1, on="trade_id", suffixes=("_m0", "_m1"))
    rows = []
    rescued = m[(m["exit_reason_m0"] == "STOP") & (m["exit_reason_m1"] != "STOP")]
    lost_tgt = m[(m["exit_reason_m0"] == "TARGET") & (m["exit_reason_m1"] != "TARGET")]
    both_tgt = m[(m["exit_reason_m0"] == "TARGET") & (m["exit_reason_m1"] == "TARGET")]
    old_tgt_new_stop = m[(m["exit_reason_m0"] == "TARGET") & (m["exit_reason_m1"] == "STOP")]
    m0_stop_m1_tgt = m[(m["exit_reason_m0"] == "STOP") & (m["exit_reason_m1"] == "TARGET")]
    for label, sub in [
        ("rescued_by_wider_stop", rescued),
        ("lost_old_target_winners", lost_tgt),
        ("both_target", both_tgt),
        ("m0_target_m1_stop", old_tgt_new_stop),
        ("m0_stop_m1_target", m0_stop_m1_tgt),
    ]:
        rows.append({
            "category": label,
            "count": len(sub),
            "m0_total_r": sub["net_R_m0"].sum() if len(sub) else 0,
            "m1_total_r": sub["net_R_m1"].sum() if len(sub) else 0,
            "delta_r": (sub["net_R_m1"] - sub["net_R_m0"]).sum() if len(sub) else 0,
        })
    return pd.DataFrame(rows)
