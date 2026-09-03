"""Opportunity coverage analysis — outcome labels only (not signal inputs)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.config import COVERAGE_DEFS


def label_meaningful_move(
    market: pd.DataFrame,
    entry_i: int,
    direction: str,
    atr: float,
    *,
    mfe_atr: float,
    mae_atr: float,
    horizon_min: int,
) -> bool:
    d = 1 if direction.upper() == "LONG" else -1
    ep = float(market.iloc[entry_i]["close"])
    end = min(len(market), entry_i + 1 + horizon_min)
    fav = 0.0
    adv = 0.0
    for j in range(entry_i + 1, end):
        hi, lo = float(market.iloc[j].high), float(market.iloc[j].low)
        if d == 1:
            fav = max(fav, (hi - ep) / atr)
            adv = max(adv, (ep - lo) / atr)
        else:
            fav = max(fav, (ep - lo) / atr)
            adv = max(adv, (hi - ep) / atr)
        if fav >= mfe_atr and adv < mae_atr:
            return True
        if adv >= mae_atr and fav < mfe_atr:
            return False
    return fav >= mfe_atr


def coverage_analysis(
    market: pd.DataFrame,
    core_entries: pd.DataFrame,
    s52_entries: pd.DataFrame,
    sample_indices: np.ndarray | None = None,
) -> pd.DataFrame:
    """Estimate meaningful moves on sampled 1M bars (analysis only)."""
    rows = []
    if sample_indices is None:
        # Sample every 30 min during RTH for feasibility
        sample_indices = np.arange(500, len(market) - 120, 30)
    for cdef in COVERAGE_DEFS:
        meaningful = 0
        captured_core = 0
        captured_s52 = 0
        for i in sample_indices:
            atr = float(market.iloc[i].get("atr", np.nan))
            if not np.isfinite(atr) or atr <= 0:
                continue
            for direction in ("LONG", "SHORT"):
                if not label_meaningful_move(
                    market,
                    int(i),
                    direction,
                    atr,
                    mfe_atr=cdef["mfe_atr"],
                    mae_atr=cdef["mae_atr"],
                    horizon_min=cdef["horizon_min"],
                ):
                    continue
                meaningful += 1
                ts = market.index[i]
                if not core_entries.empty:
                    near = (pd.to_datetime(core_entries["core_entry_ts"]) - ts).abs() <= pd.Timedelta(minutes=30)
                    if near.any():
                        captured_core += 1
                if not s52_entries.empty:
                    near = (pd.to_datetime(s52_entries["entry_timestamp"]) - ts).abs() <= pd.Timedelta(minutes=30)
                    if near.any():
                        captured_s52 += 1
        rows.append(
            {
                "definition": cdef["name"],
                "meaningful_moves_est": meaningful,
                "core_captured": captured_core,
                "s52_captured": captured_s52,
                "core_capture_rate": captured_core / meaningful if meaningful else np.nan,
                "s52_capture_rate": captured_s52 / meaningful if meaningful else np.nan,
            }
        )
    return pd.DataFrame(rows)
