"""Execution grid and combined-system comparison."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import apply_costs, performance
from phase36.outcomes import score_outcomes

from .config import ENTRY_VARIANTS, HOLD_BARS, STOP_ATRS, TARGET_RS
from .timing import _simulate_from_bar


def execution_grid(market: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        d = 1 if str(sig.direction).lower() == "long" else -1
        for stop_atr in STOP_ATRS:
            for tgt in TARGET_RS:
                for hold in HOLD_BARS:
                    for entry in ENTRY_VARIANTS:
                        sim = _simulate_from_bar(market, pos[ts], d, stop_atr=stop_atr, target_r=tgt, max_bars=hold, entry_mode=entry)
                        if not sim:
                            continue
                        rows.append(
                            {
                                "signal_type": sig.signal_type,
                                "stop_atr": stop_atr,
                                "target_r": tgt,
                                "hold_bars": hold,
                                "entry_mode": entry,
                                "realized_R": sim["realized_R"],
                            }
                        )
    return pd.DataFrame(rows)


def enrich_and_perf(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    out = score_outcomes(signals.assign(entry_price=signals.get("entry_price", market["close"])), market)
    if out.empty:
        return pd.DataFrame()
    merged = signals.merge(out, on=["signal_id" if "signal_id" in signals.columns else "marker_bar_timestamp"], how="left", suffixes=("", "_o"))
    return merged


def overlap_phase33(p41: pd.DataFrame, p37_rev: pd.DataFrame, *, window_bars: int = 2):
    if p41.empty or p37_rev.empty:
        return pd.DataFrame([{"segment": "OVERLAP", "N": 0}, {"segment": "NEW_PHASE41_ONLY", "N": len(p41)}])
    p41 = p41.copy()
    p37_rev = p37_rev.copy()
    p41["ts"] = pd.to_datetime(p41["marker_bar_timestamp"], utc=True)
    p37_rev["ts"] = pd.to_datetime(p37_rev["marker_bar_timestamp"], utc=True)
    overlap = []
    for _, row in p41.iterrows():
        want = "RL" if row.get("direction", row.get("signal_type", "")) in ("Long", "MRL") else "RS"
        win = pd.Timedelta(minutes=15 * window_bars)
        sub = p37_rev.loc[(p37_rev["signal_type"] == want) & (abs(p37_rev["ts"] - row["ts"]) <= win)]
        overlap.append(len(sub) > 0)
    p41["phase33_overlap"] = overlap
    ov = p41.loc[p41["phase33_overlap"]]
    new_only = p41.loc[~p41["phase33_overlap"]]
    return p41, ov, new_only


def combined_system_perf(p40: pd.DataFrame, p41: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, df in (("CURRENT_FROZEN_P40", p40), ("P41_ONLY", p41), ("COMBINED", pd.concat([p40, p41], ignore_index=True) if not p41.empty else p40)):
        if df is None or df.empty:
            continue
        sig = df.copy()
        if "entry_price" not in sig.columns:
            sig["entry_price"] = sig.get("entry", np.nan)
        if "stop" not in sig.columns:
            sig["stop"] = sig.get("stop_price", np.nan)
        pos = {ts: i for i, ts in enumerate(market.index)}
        out_rows = []
        for s in sig.itertuples(index=False):
            ts = pd.Timestamp(getattr(s, "marker_bar_timestamp"))
            if ts not in pos:
                continue
            d = 1 if str(getattr(s, "direction", "Long")).lower() == "long" else -1
            from .timing import _simulate_from_bar
            sim = _simulate_from_bar(market, pos[ts], d, stop_atr=0.75, target_r=2.0, max_bars=4)
            if sim:
                out_rows.append({"realized_R": sim["realized_R"], "entry_price": float(market.iloc[pos[ts]]["close"]), "stop": float(getattr(s, "stop", np.nan))})
        if not out_rows:
            continue
        merged = pd.DataFrame(out_rows)
        merged["net_R"] = apply_costs(merged.assign(stop_price=merged["stop"], result_R=merged["realized_R"]))
        rows.append({"system": name, **performance(merged, col="net_R")})
    return pd.DataFrame(rows)


import numpy as np
