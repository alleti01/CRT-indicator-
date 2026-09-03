"""Phase58D analysis outputs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics, simulate_trades
from phase58c.research.evaluation import label_meaningful_moves, move_capture_at_entry, retention_tier


def baseline_comparison_table(systems: dict[str, pd.DataFrame], opps: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    rows = []
    for name, trades in systems.items():
        m = metrics(trades["net_R"].values) if not trades.empty else dict(N=0, AvgR=0, PF=0, TotalR=0, MaxDD=0, win_rate=0)
        n_opp = len(opps[name]) if opps and name in opps else np.nan
        rows.append({
            "system": name,
            "raw_signals": np.nan,
            "opportunities": n_opp,
            "trades": m.get("N", 0),
            "AvgR": m.get("AvgR", 0),
            "PF": m.get("PF", 0),
            "TotalR": m.get("TotalR", 0),
            "MaxDD": m.get("MaxDD", 0),
            "win_rate": m.get("WinRate", m.get("win_rate", 0)),
        })
    return pd.DataFrame(rows)


def opportunity_retention_vs_c(
    opps_c_ref: pd.DataFrame,
    opps_d: pd.DataFrame,
    trades_c_ref: pd.DataFrame,
    trades_d: pd.DataFrame,
) -> pd.DataFrame:
    ref_ids = set(opps_c_ref["opportunity_id"])
    d_ids = set(opps_d["opportunity_id"])
    matched = ref_ids & d_ids
    ref_win = set(opps_c_ref.loc[opps_c_ref["has_winner"]]["opportunity_id"]) if "has_winner" in opps_c_ref else set()
    d_win = set(opps_d.loc[opps_d["traded"]]["opportunity_id"]) if "traded" in opps_d else d_ids
    win_matched = ref_win & d_ids
    rows = [
        {"metric": "overall_opportunity_retention_pct", "value": len(matched) / len(ref_ids) * 100 if ref_ids else 0},
        {"metric": "winning_opportunity_retention_pct", "value": len(win_matched) / len(ref_win) * 100 if ref_win else 0},
        {"metric": "phase58c_opportunities", "value": len(ref_ids)},
        {"metric": "phase58d_opportunities", "value": len(d_ids)},
        {"metric": "raw_signal_reduction_pct", "value": (1 - len(trades_d) / len(trades_c_ref)) * 100 if len(trades_c_ref) else 0},
    ]
    return pd.DataFrame(rows)


def timing_comparison(
    opps_c: pd.DataFrame,
    opps_d: pd.DataFrame,
    trades_d: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    merged = opps_d.merge(
        opps_c[["opportunity_id", "first_signal_i"]].rename(columns={"first_signal_i": "ref_first_i"}),
        on="opportunity_id", how="inner",
    )
    if merged.empty:
        return pd.DataFrame([{"metric": "take_vs_first_1m", "median": 0, "mean": 0}])
    take_i = merged["take_i"].fillna(merged["created_i"]).astype(int)
    delta = take_i - merged["ref_first_i"]
    rows.append({"metric": "detect_vs_first_1m", "median": float((merged["created_i"] - merged["ref_first_i"]).median()), "mean": float((merged["created_i"] - merged["ref_first_i"]).mean())})
    rows.append({"metric": "arm_vs_first_1m", "median": float((merged["armed_i"] - merged["ref_first_i"]).median()), "mean": float((merged["armed_i"] - merged["ref_first_i"]).mean())})
    rows.append({"metric": "take_vs_first_1m", "median": float(delta.median()), "mean": float(delta.mean())})
    if not trades_d.empty and "entry_i" in trades_d.columns and "signal_i" in trades_d.columns:
        rows.append({"metric": "entry_vs_first_1m", "median": float((trades_d["entry_i"] - trades_d["signal_i"]).median()), "mean": float((trades_d["entry_i"] - trades_d["signal_i"]).mean())})
    return pd.DataFrame(rows)


def move_capture_report(m, trades: pd.DataFrame, horizon: int = 60) -> pd.DataFrame:
    rows = []
    for _, t in trades.iterrows():
        si = int(t.get("signal_i", t.get("entry_i", 0)))
        ei = int(t["entry_i"])
        cap = move_capture_at_entry(si, ei, t["direction"], m.m1_hi, m.m1_lo, m.m1_cl, m.m1_atr, horizon)
        rows.append({"trade_id": t.get("trade_id", ""), **cap})
    return pd.DataFrame(rows)


def shadow_pass_analysis(rejected: pd.DataFrame, shadow_trades: pd.DataFrame) -> pd.DataFrame:
    if rejected.empty:
        return pd.DataFrame([{"metric": "pass_count", "value": 0}])
    m = metrics(shadow_trades["net_R"].values) if not shadow_trades.empty else dict(AvgR=0, TotalR=0)
    return pd.DataFrame([
        {"metric": "pass_count", "value": len(rejected)},
        {"metric": "pass_shadow_avg_r", "value": m.get("AvgR", 0)},
        {"metric": "pass_shadow_total_r", "value": m.get("TotalR", 0)},
        {"metric": "winning_pass_shadow", "value": int((shadow_trades["net_R"] > 0).sum()) if not shadow_trades.empty else 0},
        {"metric": "losing_pass_shadow", "value": int((shadow_trades["net_R"] <= 0).sum()) if not shadow_trades.empty else 0},
    ])


def evidence_retention_curve(trades: pd.DataFrame, col: str = "total_evidence") -> pd.DataFrame:
    if trades.empty or col not in trades.columns:
        return pd.DataFrame()
    rows = []
    for thr in sorted(trades[col].dropna().unique()):
        sub = trades.loc[trades[col] >= thr]
        m = metrics(sub["net_R"].values)
        rows.append({"threshold": thr, "trades": len(sub), **m})
    return pd.DataFrame(rows)


def year_stability(trades: pd.DataFrame, idx) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    t = trades.copy()
    t["year"] = [idx[int(i)].year for i in t["entry_i"]]
    rows = []
    for yr, g in t.groupby("year"):
        m = metrics(g["net_R"].values)
        rows.append({"year": yr, "trades": len(g), **m})
    return pd.DataFrame(rows)


def compare_vs_phase58b(trades_d: pd.DataFrame, trades_58b_c: pd.DataFrame) -> pd.DataFrame:
    m_d = metrics(trades_d["net_R"].values) if not trades_d.empty else {}
    m_c = metrics(trades_58b_c["net_R"].values) if not trades_58b_c.empty else {}
    return pd.DataFrame([{
        "metric": "trade_count_diff", "value": m_d.get("N", 0) - m_c.get("N", 0)},
        {"metric": "total_r_diff", "value": m_d.get("TotalR", 0) - m_c.get("TotalR", 0)},
        {"metric": "avg_r_diff", "value": m_d.get("AvgR", 0) - m_c.get("AvgR", 0)},
        {"metric": "pf_diff", "value": m_d.get("PF", 0) - m_c.get("PF", 0)},
    ])
