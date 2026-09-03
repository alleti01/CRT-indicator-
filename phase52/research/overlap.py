"""CORE overlap and portfolio analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.config import CORE_OVERLAP_MIN


def load_core_trades() -> pd.DataFrame:
    from phase48.entries import load_frozen_entries

    core = load_frozen_entries()
    core = core.rename(columns={"entry_timestamp": "core_entry_ts"})
    return core[["core_entry_ts", "direction", "B_net_R", "control_net_R"]].copy()


def classify_overlap(s52: pd.DataFrame, core: pd.DataFrame, window_min: int = CORE_OVERLAP_MIN) -> pd.DataFrame:
    if s52.empty:
        return s52
    out = s52.copy()
    out["core_overlap"] = False
    if core.empty:
        out["overlap_class"] = "S52_ONLY"
        return out
    core_ts = pd.to_datetime(core["core_entry_ts"])
    for i, row in out.iterrows():
        ts = pd.Timestamp(row["entry_timestamp"])
        delta = (core_ts - ts).abs()
        hit = delta <= pd.Timedelta(minutes=window_min)
        if not hit.any():
            out.at[i, "overlap_class"] = "S52_ONLY"
        else:
            out.at[i, "core_overlap"] = True
            # direction match?
            dirs = core.loc[hit, "direction"].str.upper()
            if (dirs == row["direction"].upper()).any():
                out.at[i, "overlap_class"] = "BOTH"
            else:
                out.at[i, "overlap_class"] = "S52_ONLY"
    return out


def overlap_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cls in ("S52_ONLY", "BOTH", "CORE_ONLY"):
        if cls == "CORE_ONLY":
            continue
        sub = trades.loc[trades.get("overlap_class", "S52_ONLY") == cls] if not trades.empty else pd.DataFrame()
        if sub.empty:
            rows.append({"class": cls, "N": 0})
            continue
        rs = sub["net_R"].astype(float)
        rows.append(
            {
                "class": cls,
                "N": len(sub),
                "AvgR": float(rs.mean()),
                "PF": float(rs[rs > 0].sum() / abs(rs[rs <= 0].sum())) if (rs <= 0).any() else np.inf,
                "TotalR": float(rs.sum()),
            }
        )
    return pd.DataFrame(rows)
