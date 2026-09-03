"""Causal opportunity clustering — no future outcome labels."""
from __future__ import annotations

import numpy as np
import pandas as pd


def cluster_1m_opportunities(
    trades: pd.DataFrame,
    armed_i: np.ndarray,
    structural_gap: int = 30,
    armed_cycle_gap: int = 5,
) -> pd.DataFrame:
    """Assign deterministic opportunity_id to each 1M trade.

    Primary grouping: same direction + gap <= structural_gap bars.
    armed_i split only applies when gap exceeds armed_cycle_gap (Phase58
    assigns a fresh armed_i per take, so armed alone must not split).
    """
    df = trades.copy()
    df["armed_i"] = armed_i
    df = df.sort_values("signal_i").reset_index(drop=True)

    opp_starts = []
    cur_dir = ""
    cur_last_si = -1
    cur_start_si = -1
    cur_armed = -1

    for _, row in df.iterrows():
        si = int(row["signal_i"])
        d = row["direction"]
        ai = int(row["armed_i"]) if pd.notna(row["armed_i"]) else -1
        new = False
        if not opp_starts:
            new = True
        elif d != cur_dir:
            new = True
        elif si - cur_last_si > structural_gap:
            new = True
        # Note: Phase58 assigns fresh armed_i per TAKE — do not split on armed_i alone.
        if new:
            cur_dir = d
            cur_armed = ai
            cur_start_si = si
        opp_starts.append(cur_start_si)
        cur_last_si = si

    df["opportunity_id"] = (
        "OPP_" + pd.Series(opp_starts).astype(int).astype(str).str.zfill(8) + "_" + df["direction"]
    )
    return df


def cluster_by_time_gap(trades: pd.DataFrame, gap_minutes: int) -> pd.DataFrame:
    """Diagnostic time-only clustering sensitivity."""
    df = trades.sort_values("signal_i").reset_index(drop=True).copy()
    opp_ids = []
    counter = 0
    cur_dir = ""
    cur_last = -1
    for _, row in df.iterrows():
        si = int(row["signal_i"])
        d = row["direction"]
        if not opp_ids or d != cur_dir or si - cur_last > gap_minutes:
            counter += 1
            cur_dir = d
        opp_ids.append(f"TIME{gap_minutes}m_{counter:06d}")
        cur_last = si
    df["opportunity_id"] = opp_ids
    return df


def summarize_opportunities(trades_with_opp: pd.DataFrame, idx: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Build opportunity-level summary from clustered trades."""
    rows = []
    for oid, g in trades_with_opp.groupby("opportunity_id", sort=False):
        g = g.sort_values("signal_i")
        first = g.iloc[0]
        last = g.iloc[-1]
        si0 = int(first["signal_i"])
        si1 = int(last["signal_i"])
        rows.append({
            "opportunity_id": oid,
            "direction": first["direction"],
            "start_signal_i": si0,
            "end_signal_i": si1,
            "first_signal_i": si0,
            "last_signal_i": si1,
            "signal_count": len(g),
            "first_signal_price": first["entry_price"],
            "last_signal_price": last["entry_price"],
            "first_entry_i": int(first["entry_i"]),
            "armed_i": int(first.get("armed_i", -1)) if pd.notna(first.get("armed_i", np.nan)) else -1,
            "winners": int((g["net_R"] > 0).sum()),
            "losers": int((g["net_R"] <= 0).sum()),
            "net_total_r": float(g["net_R"].sum()),
            "best_trade_r": float(g["net_R"].max()),
            "first_trade_r": float(first["net_R"]),
            "has_winner": bool((g["net_R"] > 0).any()),
        })
    opp = pd.DataFrame(rows)
    if idx is not None and not opp.empty:
        opp["start_timestamp"] = [str(idx[int(i)]) for i in opp["start_signal_i"]]
        opp["end_timestamp"] = [str(idx[int(i)]) for i in opp["last_signal_i"]]
        opp["first_signal_timestamp"] = opp["start_timestamp"]
        opp["last_signal_timestamp"] = opp["end_timestamp"]
    return opp


def build_signal_map(trades_with_opp: pd.DataFrame) -> pd.DataFrame:
    return trades_with_opp[
        ["trade_id", "opportunity_id", "signal_i", "entry_i", "direction", "entry_price", "net_R", "armed_i"]
    ].copy()
