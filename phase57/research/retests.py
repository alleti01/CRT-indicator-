"""Retest detection engine — T1 through T8.

Retests are interactions with specific price levels after initial structure
formation. All detection is causal (closed bars only).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase57.research.fvg import FVG
from phase57.research.legs import PriceLeg
from phase57.research.orb import ORBRange


@dataclass
class Retest:
    retest_type: str        # T1-T8
    level: float
    level_label: str        # description of the level being retested
    bar_i: int
    timestamp_ct: pd.Timestamp
    direction: str          # expected trade direction if retest holds
    distance_to_level: float
    penetration: float      # how far past the level price went
    penetration_atr: float
    duration: int           # bars spent near level
    rejection_magnitude: float  # close distance from level after interaction
    close_above_level: bool
    wick_ratio: float       # wick beyond level / total bar range
    first_reaction_dir: str # "WITH" or "AGAINST" expected direction
    retest_id: str = ""


def detect_swing_retests(
    m1: pd.DataFrame,
    legs: list[PriceLeg],
    *,
    max_bars_after: int = 30,
    proximity_atr: float = 0.3,
) -> list[Retest]:
    """T1: broken swing level retests after a leg completes."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    retests: list[Retest] = []
    counter = 0

    for leg in legs:
        if not leg.structure_broken or leg.end_i + 1 >= n:
            continue
        a = atr[leg.end_i] if np.isfinite(atr[leg.end_i]) else 1.0
        level = leg.start_price
        end = min(n, leg.end_i + 1 + max_bars_after)

        for j in range(leg.end_i + 1, end):
            bar_a = atr[j] if np.isfinite(atr[j]) else a
            if leg.direction == "BULL":
                dist = cl[j] - level
                pen = max(0.0, level - lo[j])
                close_above = cl[j] >= level
                expected_dir = "LONG"
                wick = max(0.0, level - lo[j])
            else:
                dist = level - cl[j]
                pen = max(0.0, hi[j] - level)
                close_above = cl[j] <= level
                expected_dir = "SHORT"
                wick = max(0.0, hi[j] - level)

            if abs(dist) / bar_a > proximity_atr and pen / bar_a < 0.05:
                continue

            bar_range = hi[j] - lo[j]
            wick_rat = wick / bar_range if bar_range > 0 else 0.0
            rej = abs(dist)

            if j + 1 < n:
                if leg.direction == "BULL":
                    react = "WITH" if cl[j + 1] > cl[j] else "AGAINST"
                else:
                    react = "WITH" if cl[j + 1] < cl[j] else "AGAINST"
            else:
                react = "UNKNOWN"

            counter += 1
            retests.append(Retest(
                retest_type="T1",
                level=level,
                level_label=f"broken_swing_{leg.direction}",
                bar_i=j,
                timestamp_ct=idx[j],
                direction=expected_dir,
                distance_to_level=dist,
                penetration=pen,
                penetration_atr=pen / bar_a,
                duration=1,
                rejection_magnitude=rej,
                close_above_level=close_above,
                wick_ratio=wick_rat,
                first_reaction_dir=react,
                retest_id=f"RT-{counter:07d}",
            ))
            break  # one retest per leg
    return retests


def detect_fvg_retests(
    m1: pd.DataFrame,
    fvgs: list[FVG],
    *,
    max_bars_after: int = 60,
) -> list[Retest]:
    """T3: FVG zone retests — price returns to an unfilled FVG."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    retests: list[Retest] = []
    counter = 0

    for fvg in fvgs:
        if fvg.filled or fvg.formation_i + 1 >= n:
            continue
        end = min(n, fvg.formation_i + 1 + max_bars_after)
        a = atr[fvg.formation_i] if np.isfinite(atr[fvg.formation_i]) else 1.0

        for j in range(fvg.formation_i + 1, end):
            touched = False
            if fvg.direction == "BULL" and lo[j] <= fvg.upper:
                touched = True
                pen = max(0.0, fvg.upper - lo[j])
                expected_dir = "LONG"
                close_above = cl[j] >= fvg.midpoint
            elif fvg.direction == "BEAR" and hi[j] >= fvg.lower:
                touched = True
                pen = max(0.0, hi[j] - fvg.lower)
                expected_dir = "SHORT"
                close_above = cl[j] <= fvg.midpoint
            if not touched:
                continue

            bar_a = atr[j] if np.isfinite(atr[j]) else a
            bar_range = hi[j] - lo[j]
            wick = pen
            wick_rat = wick / bar_range if bar_range > 0 else 0.0
            dist = abs(cl[j] - fvg.midpoint)
            if j + 1 < n:
                if expected_dir == "LONG":
                    react = "WITH" if cl[j + 1] > cl[j] else "AGAINST"
                else:
                    react = "WITH" if cl[j + 1] < cl[j] else "AGAINST"
            else:
                react = "UNKNOWN"

            counter += 1
            retests.append(Retest(
                retest_type="T3",
                level=fvg.midpoint,
                level_label=f"fvg_{fvg.direction}_{fvg.timeframe}",
                bar_i=j,
                timestamp_ct=idx[j],
                direction=expected_dir,
                distance_to_level=dist,
                penetration=pen,
                penetration_atr=pen / bar_a,
                duration=1,
                rejection_magnitude=abs(cl[j] - fvg.midpoint),
                close_above_level=close_above,
                wick_ratio=wick_rat,
                first_reaction_dir=react,
                retest_id=f"RT-{counter:07d}",
            ))
            break  # one retest per FVG
    return retests


def detect_orb_retests(
    m1: pd.DataFrame,
    orb_ranges: list[ORBRange],
    *,
    max_bars: int = 200,
) -> list[Retest]:
    """T4: ORB boundary retests after initial breakout."""
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    retests: list[Retest] = []
    counter = 0

    for orb in orb_ranges:
        if orb.first_high_break_i is None and orb.first_low_break_i is None:
            continue
        # Retest high boundary after breakout
        if orb.first_high_break_i is not None:
            end = min(n, orb.first_high_break_i + 1 + max_bars)
            a = atr[orb.first_high_break_i] if np.isfinite(atr[orb.first_high_break_i]) else 1.0
            for j in range(orb.first_high_break_i + 1, end):
                if idx[j].date() != orb.date:
                    break
                if lo[j] <= orb.or_high and cl[j] > orb.or_high:
                    bar_a = atr[j] if np.isfinite(atr[j]) else a
                    pen = max(0.0, orb.or_high - lo[j])
                    react = "WITH" if j + 1 < n and cl[j + 1] > cl[j] else "AGAINST"
                    counter += 1
                    retests.append(Retest(
                        retest_type="T4",
                        level=orb.or_high,
                        level_label="orb_high",
                        bar_i=j,
                        timestamp_ct=idx[j],
                        direction="LONG",
                        distance_to_level=cl[j] - orb.or_high,
                        penetration=pen,
                        penetration_atr=pen / bar_a,
                        duration=1,
                        rejection_magnitude=cl[j] - orb.or_high,
                        close_above_level=True,
                        wick_ratio=pen / (hi[j] - lo[j]) if (hi[j] - lo[j]) > 0 else 0,
                        first_reaction_dir=react,
                        retest_id=f"RT-{counter:07d}",
                    ))
                    break
        # Retest low boundary after breakdown
        if orb.first_low_break_i is not None:
            end = min(n, orb.first_low_break_i + 1 + max_bars)
            a = atr[orb.first_low_break_i] if np.isfinite(atr[orb.first_low_break_i]) else 1.0
            for j in range(orb.first_low_break_i + 1, end):
                if idx[j].date() != orb.date:
                    break
                if hi[j] >= orb.or_low and cl[j] < orb.or_low:
                    bar_a = atr[j] if np.isfinite(atr[j]) else a
                    pen = max(0.0, hi[j] - orb.or_low)
                    react = "WITH" if j + 1 < n and cl[j + 1] < cl[j] else "AGAINST"
                    counter += 1
                    retests.append(Retest(
                        retest_type="T4",
                        level=orb.or_low,
                        level_label="orb_low",
                        bar_i=j,
                        timestamp_ct=idx[j],
                        direction="SHORT",
                        distance_to_level=orb.or_low - cl[j],
                        penetration=pen,
                        penetration_atr=pen / bar_a,
                        duration=1,
                        rejection_magnitude=orb.or_low - cl[j],
                        close_above_level=False,
                        wick_ratio=pen / (hi[j] - lo[j]) if (hi[j] - lo[j]) > 0 else 0,
                        first_reaction_dir=react,
                        retest_id=f"RT-{counter:07d}",
                    ))
                    break
    return retests


def retests_to_df(retests: list[Retest]) -> pd.DataFrame:
    return pd.DataFrame([{
        "retest_id": r.retest_id,
        "retest_type": r.retest_type,
        "level": r.level,
        "level_label": r.level_label,
        "bar_i": r.bar_i,
        "timestamp_ct": r.timestamp_ct,
        "direction": r.direction,
        "distance_to_level": r.distance_to_level,
        "penetration": r.penetration,
        "penetration_atr": r.penetration_atr,
        "duration": r.duration,
        "rejection_magnitude": r.rejection_magnitude,
        "close_above_level": r.close_above_level,
        "wick_ratio": r.wick_ratio,
        "first_reaction_dir": r.first_reaction_dir,
    } for r in retests])
