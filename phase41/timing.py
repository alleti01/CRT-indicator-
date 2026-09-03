"""Decision timing analysis on major reversals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import LABEL_RISK_ATR


def _simulate_from_bar(market: pd.DataFrame, i: int, direction: int, *, stop_atr: float = 0.75, target_r: float = 2.0, max_bars: int = 4, entry_mode: str = "CURRENT") -> dict:
    if entry_mode == "NEXT_OPEN" and i + 1 < len(market):
        entry_i = i + 1
        entry = float(market.iloc[entry_i]["open"])
        start_j = entry_i + 1
    else:
        entry_i = i
        entry = float(market.iloc[i]["close"])
        start_j = i + 1
    atr = float(market.iloc[entry_i]["atr"])
    risk = stop_atr * atr
    if risk <= 0:
        return {}
    stop = entry - risk if direction == 1 else entry + risk
    target = entry + target_r * risk if direction == 1 else entry - target_r * risk
    mfe = mae = 0.0
    realized = 0.0
    for elapsed, j in enumerate(range(start_j, min(len(market), entry_i + max_bars + 1)), start=1):
        bar = market.iloc[j]
        hi, lo, cl = float(bar.high), float(bar.low), float(bar.close)
        if direction == 1:
            mfe = max(mfe, (hi - entry) / risk)
            mae = max(mae, (entry - lo) / risk)
            if lo <= stop:
                realized = -1.0
                break
            if hi >= target:
                realized = target_r
                break
        else:
            mfe = max(mfe, (entry - lo) / risk)
            mae = max(mae, (hi - entry) / risk)
            if hi >= stop:
                realized = -1.0
                break
            if lo <= target:
                realized = target_r
                break
        if elapsed >= max_bars:
            realized = (cl - entry) / risk * direction
            break
    return {"realized_R": realized, "MFE_R": mfe, "MAE_R": mae, "entry_bar": entry_i}


def decision_timing_comparison(market: pd.DataFrame, opportunities: pd.DataFrame) -> pd.DataFrame:
    pos = {ts: i for i, ts in enumerate(market.index)}
    variants = (
        ("TURN_BAR_CLOSE", 0, "CURRENT"),
        ("PLUS_1_BAR", 1, "CURRENT"),
        ("PLUS_2_BARS", 2, "CURRENT"),
        ("NEXT_OPEN", 0, "NEXT_OPEN"),
    )
    rows = []
    for opp in opportunities.itertuples(index=False):
        ts = pd.Timestamp(opp.extreme_timestamp)
        if ts not in pos:
            continue
        ei = pos[ts]
        d = 1 if opp.direction == "Long" else -1
        extreme_px = float(opp.extreme_price)
        for name, offset, emode in variants:
            bi = ei + offset
            if bi >= len(market):
                continue
            sim = _simulate_from_bar(market, bi, d, entry_mode=emode)
            if not sim:
                continue
            entry = float(market.iloc[sim["entry_bar"]]["close"] if emode == "CURRENT" else market.iloc[min(sim["entry_bar"], len(market)-1)]["open"])
            delay_bars = sim["entry_bar"] - ei
            price_giveup_atr = abs(entry - extreme_px) / float(market.iloc[ei]["atr"]) if float(market.iloc[ei]["atr"]) > 0 else np.nan
            rows.append(
                {
                    "event_id": opp.event_id,
                    "direction": opp.direction,
                    "timing_variant": name,
                    "delay_bars_from_extreme": delay_bars,
                    "price_giveup_atr": price_giveup_atr,
                    **sim,
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    summary = out.groupby("timing_variant").agg(
        N=("realized_R", "count"),
        AvgR=("realized_R", "mean"),
        median_delay=("delay_bars_from_extreme", "median"),
        median_giveup_atr=("price_giveup_atr", "median"),
        MFE=("MFE_R", "mean"),
        MAE=("MAE_R", "mean"),
    ).reset_index()
    return summary.merge(out, on="timing_variant", how="left", suffixes=("_summary", ""))
