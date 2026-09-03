"""Phase61 — opportunity clustering and first-vs-later analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58d.research.opportunity_memory import OpportunityMemory


def cluster_signals(signals: pd.DataFrame, structural_gap: int = 30, expire_bars: int = 45) -> pd.DataFrame:
    mem = OpportunityMemory(structural_gap=structural_gap, expire_bars=expire_bars)
    rows = []
    for _, row in signals.sort_values("signal_i").iterrows():
        si = int(row["signal_i"])
        price = float(row["entry_price"])
        direction = row["direction"]
        mem.expire_stale(si)
        opp, is_new = mem.match_or_create(si, price, direction)
        rank = opp.signal_count
        rows.append(
            {
                "signal_i": si,
                "opportunity_id": opp.opportunity_id,
                "opp_rank": rank,
                "is_first": rank == 1,
                "is_new": is_new,
                "opp_created_i": opp.created_i,
                "opp_created_price": opp.created_price,
            }
        )
    return signals.merge(pd.DataFrame(rows), on="signal_i", how="left")


def clustering_stats(clustered: pd.DataFrame) -> dict:
    raw = len(clustered)
    n_opp = clustered["opportunity_id"].nunique()
    per_opp = clustered.groupby("opportunity_id").size()
    redundancy = 1.0 - n_opp / raw if raw else 0.0
    return {
        "raw_signals": raw,
        "unique_opportunities": int(n_opp),
        "redundancy_pct": round(redundancy * 100, 2),
        "mean_signals_per_opp": float(per_opp.mean()),
        "median_signals_per_opp": float(per_opp.median()),
    }


def first_vs_later(paths: pd.DataFrame, clustered: pd.DataFrame) -> dict:
    df = paths.merge(clustered[["signal_i", "opp_rank", "opportunity_id", "opp_created_price"]], on="signal_i")
    out = {}
    for rank, label in [(1, "first"), (2, "second"), (3, "third")]:
        sub = df[df["opp_rank"] == rank]
        if sub.empty:
            out[label] = {}
            continue
        out[label] = {
            "n": len(sub),
            "dir_acc_15m": float(sub["dir_ok_15m"].mean()),
            "dir_acc_60m": float(sub["dir_ok_60m"].mean()) if "dir_ok_60m" in sub.columns else None,
            "median_mfe_60m": float(sub["mfe_60m_atr"].median()),
            "median_mae_60m": float(sub["mae_60m_atr"].median()),
            "median_potential_r": float(sub["mfe_60m_atr"].median()),
            "median_chase_atr": float(
                ((sub["entry_price"] - sub["opp_created_price"]).abs() / sub["atr"]).median()
            ),
        }
    last = df.loc[df.groupby("opportunity_id")["opp_rank"].idxmax()]
    out["last"] = {
        "n": len(last),
        "median_mfe_60m": float(last["mfe_60m_atr"].median()),
        "median_mae_60m": float(last["mae_60m_atr"].median()),
        "median_chase_atr": float(
            ((last["entry_price"] - last["opp_created_price"]).abs() / last["atr"]).median()
        ),
    }

    first = df[df["opp_rank"] == 1][["opportunity_id", "mfe_60m_atr", "entry_price"]]
    last2 = df.loc[df.groupby("opportunity_id")["opp_rank"].idxmax()][
        ["opportunity_id", "mfe_60m_atr", "entry_price"]
    ]
    merged = first.merge(last2, on="opportunity_id", suffixes=("_first", "_last"))
    wait_improves = float((merged["mfe_60m_atr_last"] > merged["mfe_60m_atr_first"]).mean()) if len(merged) else 0
    out["waiting_improves_mfe"] = wait_improves > 0.5
    out["waiting_improves_mfe_pct"] = wait_improves
    out["median_damage_from_waiting_atr"] = float(
        (merged["entry_price_last"] - merged["entry_price_first"]).abs().median()
    )
    return out
