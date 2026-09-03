"""Scan displacement events and causal swing BOS for Phase 33."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.bos_semantic_audit import CausalSwingEngine
from phase16.indicators import confirmed_pivots, is_in_session

from .config import (
    BODY_AVG_LOOKBACK,
    BODY_MULTIPLIER,
    CLOSE_LOC_LONG_MIN,
    CLOSE_LOC_SHORT_MAX,
    OPP_BOS_MAX_BARS,
    RTH_SESSION,
)


def scan_displacements(market: pd.DataFrame) -> pd.DataFrame:
    """All RTH displacement bars — same definition as Phase 31."""
    body = (market["close"] - market["open"]).abs()
    avg_body = body.rolling(BODY_AVG_LOOKBACK, min_periods=BODY_AVG_LOOKBACK).mean()
    rng = (market["high"] - market["low"]).replace(0, np.nan)
    cl = (market["close"] - market["low"]) / rng
    rows: List[dict] = []
    for i in range(BODY_AVG_LOOKBACK, len(market)):
        ts = market.index[i]
        if not is_in_session(ts, RTH_SESSION):
            continue
        if not np.isfinite(avg_body.iloc[i]) or body.iloc[i] <= BODY_MULTIPLIER * avg_body.iloc[i]:
            continue
        if cl.iloc[i] >= CLOSE_LOC_LONG_MIN:
            disp_dir = "Long"
        elif cl.iloc[i] <= CLOSE_LOC_SHORT_MAX:
            disp_dir = "Short"
        else:
            continue
        o, h, l, c = market.iloc[i][["open", "high", "low", "close"]]
        rows.append(
            {
                "displacement_id": len(rows) + 1,
                "displacement_timestamp": ts,
                "bar_index": i,
                "displacement_direction": disp_dir,
                "open": float(o),
                "high": float(h),
                "low": float(l),
                "close": float(c),
                "midpoint": float((h + l) / 2.0),
                "body": float(body.iloc[i]),
                "avg_body": float(avg_body.iloc[i]),
                "body_ratio": float(body.iloc[i] / avg_body.iloc[i]),
                "close_location": float(cl.iloc[i]),
                "atr": float(market["atr"].iloc[i]) if np.isfinite(market["atr"].iloc[i]) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def precompute_opposite_bos(market: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[int, List[dict]]]:
    """Causal SWING_2_2 BOS events indexed by bar."""
    ph = confirmed_pivots(market["high"], 2, 2, "high")
    pl = confirmed_pivots(market["low"], 2, 2, "low")
    engine = CausalSwingEngine(2, 2)
    rows: List[dict] = []
    by_bar: Dict[int, List[dict]] = {}
    for i, ts in enumerate(market.index):
        bull, bear, _ = engine.step(
            bar_index=i,
            timestamp=ts,
            index=market.index,
            close=float(market["close"].iloc[i]),
            pivot_high=float(ph.iloc[i]) if np.isfinite(ph.iloc[i]) else np.nan,
            pivot_low=float(pl.iloc[i]) if np.isfinite(pl.iloc[i]) else np.nan,
        )
        for evt, direction in ((bull, "Long"), (bear, "Short")):
            if evt is None:
                continue
            row = {
                "bos_bar_index": i,
                "bos_timestamp": ts,
                "bos_direction": direction,
                "bos_level": float(evt.level),
                "is_choch": bool(evt.is_choch),
            }
            rows.append(row)
            by_bar.setdefault(i, []).append(row)
    return pd.DataFrame(rows), by_bar


def first_opposite_bos(
    disp_bar: int,
    disp_direction: str,
    bos_events: pd.DataFrame,
    *,
    max_bars: int = OPP_BOS_MAX_BARS,
) -> Optional[dict]:
    opp = "Long" if disp_direction == "Short" else "Short"
    sub = bos_events.loc[
        (bos_events.bos_bar_index > disp_bar)
        & (bos_events.bos_bar_index <= disp_bar + max_bars)
        & (bos_events.bos_direction == opp)
    ]
    if sub.empty:
        return None
    row = sub.iloc[0]
    return row.to_dict()


def reversal_direction(displacement_direction: str) -> str:
    return "Long" if displacement_direction == "Short" else "Short"
