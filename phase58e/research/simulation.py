"""Shadow trade simulation — same entry, flipped direction."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.precompute import MTFArrays
from phase58b.research.simulation import metrics, simulate_trades


def build_shadow_executions(
    trades: pd.DataFrame,
    audit: pd.DataFrame,
    direction_col: str,
    system: str,
) -> pd.DataFrame:
    """Build execution records using shadow direction at same entry_i/price."""
    merged = trades.merge(
        audit[["opportunity_id", direction_col, "direction_relation", "market_state"]],
        on="opportunity_id",
        how="inner",
        suffixes=("", "_audit"),
    )
    rows = []
    for _, r in merged.iterrows():
        shadow_dir = r[direction_col]
        if shadow_dir == "UNCERTAIN":
            shadow_dir = r["direction"]  # keep original for uncertain shadow book
        rows.append({
            "opportunity_id": r["opportunity_id"],
            "setup_id": r["opportunity_id"],
            "direction": shadow_dir,
            "original_direction": r["direction"],
            "signal_i": int(r["signal_m1_i"]),
            "signal_m1_i": int(r["signal_m1_i"]),
            "entry_i": int(r["entry_i"]),
            "entry_price": float(r["entry_price"]),
            "variant": system,
            "tag": r.get("direction_relation", ""),
            "market_state": r.get("market_state", ""),
            "flipped": shadow_dir != r["direction"],
        })
    return pd.DataFrame(rows)


def flip_categories(audit: pd.DataFrame, trades: pd.DataFrame, flip_sim: pd.DataFrame | None = None) -> pd.DataFrame:
    """SAME_CORRECT / SAME_WRONG / FLIP_CORRECT / FLIP_WRONG."""
    m = trades.merge(audit[["opportunity_id", "shadow_direction_t0", "direction_relation"]], on="opportunity_id")
    flip_lookup = {}
    if flip_sim is not None and not flip_sim.empty and "opportunity_id" in flip_sim.columns:
        flip_lookup = flip_sim.set_index("opportunity_id")["net_R"].to_dict()
    rows = []
    for _, r in m.iterrows():
        orig_r = r["net_R"]
        flipped = r["direction_relation"] == "FLIPPED"
        if r["shadow_direction_t0"] == "UNCERTAIN":
            cat = "UNCERTAIN"
        elif not flipped:
            cat = "SAME_CORRECT" if orig_r > 0 else "SAME_WRONG"
        else:
            flip_r = flip_lookup.get(r["opportunity_id"])
            if flip_r is not None:
                cat = "FLIP_CORRECT" if flip_r > orig_r else "FLIP_WRONG"
            else:
                cat = "FLIP_CORRECT" if orig_r <= 0 else "FLIP_WRONG"
        rows.append({"opportunity_id": r["opportunity_id"], "category": cat, "original_net_R": orig_r, "direction_relation": r["direction_relation"]})
    return pd.DataFrame(rows)


def simulate_flip_outcomes(m: MTFArrays, trades: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """For flipped opps, simulate opposite direction at same entry."""
    rows = []
    for _, t in trades.iterrows():
        d = "SHORT" if t["direction"] == "LONG" else "LONG"
        rows.append({
            "setup_id": t.get("opportunity_id", t.get("setup_id", "")),
            "direction": d,
            "signal_i": int(t["signal_m1_i"]),
            "entry_i": int(t["entry_i"]),
            "entry_price": float(t["entry_price"]),
            "variant": "FLIP_SHADOW",
        })
    flip_trades = simulate_trades(m, pd.DataFrame(rows), cfg, "FLIP")
    if flip_trades.empty:
        return flip_trades
    if "setup_id" in flip_trades.columns:
        flip_trades = flip_trades.rename(columns={"setup_id": "opportunity_id"})
    flip_trades = flip_trades.merge(
        trades[["opportunity_id", "net_R", "direction"]].rename(
            columns={"net_R": "original_net_R", "direction": "original_direction"}),
        on="opportunity_id", how="left",
    )
    flip_trades["flip_delta_R"] = flip_trades["net_R"] - flip_trades["original_net_R"]
    return flip_trades
