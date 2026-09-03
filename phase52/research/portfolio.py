"""Portfolio analysis: CORE, S52, CORE+S52."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.research.metrics import max_dd, pf, summarize_trades


def merge_portfolio(
    core: pd.DataFrame,
    s52: pd.DataFrame,
    *,
    conflict: str = "prefer_core",
) -> pd.DataFrame:
    """Combine trades chronologically with conflict handling."""
    c = core.copy()
    c["model"] = "CORE"
    c["entry_timestamp"] = pd.to_datetime(c["core_entry_ts"] if "core_entry_ts" in c.columns else c["entry_timestamp"])
    c["net_R"] = c["control_net_R"].astype(float) if "control_net_R" in c.columns else c["B_net_R"].astype(float)
    s = s52.copy()
    s["model"] = "S52"
    s["entry_timestamp"] = pd.to_datetime(s["entry_timestamp"])
    cols = ["entry_timestamp", "direction", "net_R", "model"]
    all_t = pd.concat([c[cols], s[cols]], ignore_index=True).sort_values("entry_timestamp")
    if all_t.empty:
        return all_t
    kept: list[dict] = []
    for _, row in all_t.iterrows():
        if not kept:
            kept.append(row.to_dict())
            continue
        prev = kept[-1]
        delta = (row["entry_timestamp"] - pd.Timestamp(prev["entry_timestamp"])).total_seconds() / 60.0
        if delta <= 30 and row["direction"] != prev["direction"]:
            if conflict == "prefer_core":
                if row["model"] == "CORE":
                    kept[-1] = row.to_dict()
                # else skip s52 opposite
            elif conflict == "prefer_s52":
                if row["model"] == "S52":
                    kept[-1] = row.to_dict()
            continue
        if delta <= 30 and row["direction"] == prev["direction"] and row["model"] == prev["model"]:
            continue
        if delta <= 30 and row["direction"] == prev["direction"] and row["model"] != prev["model"]:
            if conflict == "prefer_core" and prev["model"] == "CORE":
                continue
            if conflict == "prefer_core" and row["model"] == "CORE":
                kept[-1] = row.to_dict()
                continue
        kept.append(row.to_dict())
    return pd.DataFrame(kept)


def portfolio_summary(trades: pd.DataFrame) -> dict:
    return summarize_trades(trades)
