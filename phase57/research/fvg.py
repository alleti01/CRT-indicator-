"""Fair Value Gap (FVG) detection and interaction classification.

Standard 3-candle imbalance: FVG exists only after candle 3 closes.
Runs on 1M, 5M, and 15M timeframes with causal HTF alignment.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# ── FVG record ────────────────────────────────────────────────────────


@dataclass
class FVG:
    direction: str          # "BULL" or "BEAR"
    formation_i: int        # bar index of candle 3 (confirmation bar)
    formation_ts: pd.Timestamp
    upper: float            # top of gap
    lower: float            # bottom of gap
    midpoint: float
    size_pts: float
    size_atr: float
    impulse_body: float     # |close - open| of candle 2 (impulse)
    impulse_body_atr: float
    timeframe: str          # "1M", "5M", "15M"
    filled: bool = False
    fill_i: int | None = None
    first_revisit_i: int | None = None
    touch_count: int = 0
    max_fill_depth: float = 0.0


# ── Detection ─────────────────────────────────────────────────────────


def detect_fvgs(
    ohlc: pd.DataFrame,
    *,
    timeframe: str = "1M",
    start_i: int = 2,
) -> list[FVG]:
    """Detect all 3-candle FVGs on closed bars. Causal: uses bars [i-2, i-1, i]."""
    hi = ohlc["high"].values.astype(float)
    lo = ohlc["low"].values.astype(float)
    cl = ohlc["close"].values.astype(float)
    op = ohlc["open"].values.astype(float)
    atr = ohlc["atr"].values.astype(float) if "atr" in ohlc.columns else np.full(len(ohlc), np.nan)
    idx = ohlc.index
    n = len(ohlc)
    fvgs: list[FVG] = []

    for i in range(max(start_i, 2), n):
        a = float(atr[i]) if np.isfinite(atr[i]) and atr[i] > 0 else 1.0
        # Bullish FVG: high of candle 1 < low of candle 3
        if hi[i - 2] < lo[i]:
            body2 = abs(cl[i - 1] - op[i - 1])
            fvgs.append(FVG(
                direction="BULL",
                formation_i=i,
                formation_ts=idx[i],
                upper=float(lo[i]),
                lower=float(hi[i - 2]),
                midpoint=(float(lo[i]) + float(hi[i - 2])) / 2,
                size_pts=float(lo[i]) - float(hi[i - 2]),
                size_atr=(float(lo[i]) - float(hi[i - 2])) / a,
                impulse_body=body2,
                impulse_body_atr=body2 / a,
                timeframe=timeframe,
            ))
        # Bearish FVG: low of candle 1 > high of candle 3
        if lo[i - 2] > hi[i]:
            body2 = abs(cl[i - 1] - op[i - 1])
            fvgs.append(FVG(
                direction="BEAR",
                formation_i=i,
                formation_ts=idx[i],
                upper=float(lo[i - 2]),
                lower=float(hi[i]),
                midpoint=(float(lo[i - 2]) + float(hi[i])) / 2,
                size_pts=float(lo[i - 2]) - float(hi[i]),
                size_atr=(float(lo[i - 2]) - float(hi[i])) / a,
                impulse_body=body2,
                impulse_body_atr=body2 / a,
                timeframe=timeframe,
            ))
    return fvgs


def detect_fvgs_multitf(
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
) -> list[FVG]:
    """Detect FVGs across 1M, 5M, 15M with causal HTF alignment."""
    all_fvgs = detect_fvgs(m1, timeframe="1M")
    all_fvgs.extend(detect_fvgs(m5, timeframe="5M"))
    all_fvgs.extend(detect_fvgs(m15, timeframe="15M"))
    return all_fvgs


# ── Interaction tracking ──────────────────────────────────────────────


def classify_interaction(fvg: FVG, bar_hi: float, bar_lo: float) -> str | None:
    """Classify how a single bar interacts with an FVG zone.

    Returns interaction type or None if no interaction.
    F1=edge touch, F2=partial, F3=midpoint, F4=deep, F5=full fill,
    F7=rejection, F8=trade-through.
    """
    if fvg.direction == "BULL":
        if bar_lo > fvg.upper:
            return None
        if bar_lo > fvg.lower:
            depth = (fvg.upper - bar_lo) / fvg.size_pts if fvg.size_pts > 0 else 0
            if depth < 0.1:
                return "F1"
            if depth < 0.4:
                return "F2"
            if depth < 0.6:
                return "F3"
            if depth < 0.9:
                return "F4"
            return "F5"
        return "F8"
    else:  # BEAR
        if bar_hi < fvg.lower:
            return None
        if bar_hi < fvg.upper:
            depth = (bar_hi - fvg.lower) / fvg.size_pts if fvg.size_pts > 0 else 0
            if depth < 0.1:
                return "F1"
            if depth < 0.4:
                return "F2"
            if depth < 0.6:
                return "F3"
            if depth < 0.9:
                return "F4"
            return "F5"
        return "F8"


def track_fvg_interactions(
    fvgs: list[FVG],
    ohlc: pd.DataFrame,
    *,
    max_age_bars: int = 500,
) -> pd.DataFrame:
    """Track FVG lifecycle: first revisit, touch count, fill depth, interactions."""
    hi = ohlc["high"].values.astype(float)
    lo = ohlc["low"].values.astype(float)
    cl = ohlc["close"].values.astype(float)
    n = len(ohlc)
    records: list[dict] = []

    for fvg in fvgs:
        first_interaction = None
        first_interaction_type = None
        end = min(n, fvg.formation_i + 1 + max_age_bars)
        for j in range(fvg.formation_i + 1, end):
            itype = classify_interaction(fvg, hi[j], lo[j])
            if itype is not None:
                fvg.touch_count += 1
                if fvg.first_revisit_i is None:
                    fvg.first_revisit_i = j
                    first_interaction = j
                    first_interaction_type = itype
                if fvg.direction == "BULL":
                    depth = (fvg.upper - lo[j]) / fvg.size_pts if fvg.size_pts > 0 else 0
                else:
                    depth = (hi[j] - fvg.lower) / fvg.size_pts if fvg.size_pts > 0 else 0
                fvg.max_fill_depth = max(fvg.max_fill_depth, depth)
                if itype in ("F5", "F8"):
                    fvg.filled = True
                    fvg.fill_i = j
                    # Check for reclaim (F6): close back on FVG side after fill
                    if j + 1 < n:
                        if fvg.direction == "BULL" and cl[j + 1] > fvg.lower:
                            first_interaction_type = "F6"
                        elif fvg.direction == "BEAR" and cl[j + 1] < fvg.upper:
                            first_interaction_type = "F6"
                    break
                # Rejection: price touches then closes back on FVG side strongly
                if fvg.direction == "BULL" and cl[j] > fvg.midpoint:
                    if first_interaction_type == itype:
                        first_interaction_type = "F7"
                elif fvg.direction == "BEAR" and cl[j] < fvg.midpoint:
                    if first_interaction_type == itype:
                        first_interaction_type = "F7"

        age = (first_interaction - fvg.formation_i) if first_interaction else None
        untouched = fvg.touch_count == 0
        records.append({
            "direction": fvg.direction,
            "timeframe": fvg.timeframe,
            "formation_i": fvg.formation_i,
            "formation_ts": fvg.formation_ts,
            "upper": fvg.upper,
            "lower": fvg.lower,
            "midpoint": fvg.midpoint,
            "size_pts": fvg.size_pts,
            "size_atr": fvg.size_atr,
            "impulse_body_atr": fvg.impulse_body_atr,
            "first_revisit_i": fvg.first_revisit_i,
            "first_revisit_age": age,
            "first_interaction_type": first_interaction_type,
            "touch_count": fvg.touch_count,
            "max_fill_depth": fvg.max_fill_depth,
            "filled": fvg.filled,
            "untouched_before_revisit": untouched,
        })
    return pd.DataFrame(records)


def fvg_events_df(fvgs: list[FVG]) -> pd.DataFrame:
    """Convert FVG list to DataFrame for parquet export."""
    return pd.DataFrame([{
        "direction": f.direction,
        "timeframe": f.timeframe,
        "formation_i": f.formation_i,
        "formation_ts": f.formation_ts,
        "upper": f.upper,
        "lower": f.lower,
        "midpoint": f.midpoint,
        "size_pts": f.size_pts,
        "size_atr": f.size_atr,
        "impulse_body": f.impulse_body,
        "impulse_body_atr": f.impulse_body_atr,
    } for f in fvgs])
