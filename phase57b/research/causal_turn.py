"""Causal turn detection — the core Phase57B problem.

Given a completed Leg1 and an active pullback, identify the EARLIEST causal
evidence that the pullback may be ending and the next leg beginning.

All evidence must be available at decision time (closed bars only).
No retrospective pullback extreme labeling.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from phase57.research.legs import PriceLeg
from phase57b.config import PULLBACK_MIN_DEPTH_PCT


class TurnType(str, Enum):
    T0_QUALIFICATION = "T0"   # first bar reaching pullback threshold
    T1_CLOSE_REVERSAL = "T1"  # first close back toward leg direction
    T2_BODY_REVERSAL = "T2"   # first body > threshold in leg direction
    T3_WICK_REJECTION = "T3"  # wick rejection at pullback extreme
    T4_SWING_RECLAIM = "T4"   # close reclaims pre-pullback swing


@dataclass
class CausalTurn:
    turn_type: TurnType
    leg: PriceLeg
    qualification_i: int     # bar where pullback first reached min depth
    turn_i: int              # bar where turn evidence appeared
    entry_i: int             # executable entry = turn_i (signal on close, enter same close)
    direction: str           # "LONG" or "SHORT"
    leg_distance_atr: float
    pullback_depth_at_turn: float   # depth at turn_i / ATR
    pullback_depth_pct: float       # depth at turn_i / leg distance
    bars_in_pullback: int
    turn_id: str = ""


def detect_causal_turns(
    m1: pd.DataFrame,
    legs: list[PriceLeg],
    *,
    min_depth_pct: float = PULLBACK_MIN_DEPTH_PCT,
    max_pullback_bars: int = 60,
    body_threshold_atr: float = 0.3,
    wick_threshold_pct: float = 0.5,
) -> list[CausalTurn]:
    """Detect causal turn evidence after Leg1 pullback — NO future information.

    Sequential scan: at each bar after Leg1 ends, check:
    1. Has pullback reached minimum depth? (qualification)
    2. After qualification, does this bar show turn evidence?

    The turn is declared on the bar where evidence appears.
    Entry price = close of that bar (knowable at bar close).
    """
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    turns: list[CausalTurn] = []
    counter = 0

    for leg in legs:
        if leg.end_i + 2 >= n - 61:
            continue
        a = atr[leg.end_i] if np.isfinite(atr[leg.end_i]) and atr[leg.end_i] > 0 else 1.0
        threshold = leg.distance * min_depth_pct
        d = 1 if leg.direction == "BULL" else -1
        trade_dir = "LONG" if leg.direction == "BULL" else "SHORT"
        end = min(n - 61, leg.end_i + 1 + max_pullback_bars)

        qualified = False
        qual_i = None
        max_depth = 0.0
        deepest_so_far_price = leg.end_price

        for j in range(leg.end_i + 1, end):
            bar_a = atr[j] if np.isfinite(atr[j]) and atr[j] > 0 else a

            # Track current pullback depth (what we KNOW at bar j)
            if leg.direction == "BULL":
                current_depth = leg.end_price - lo[j]
                if lo[j] < deepest_so_far_price:
                    deepest_so_far_price = lo[j]
                depth_from_deepest = leg.end_price - deepest_so_far_price
            else:
                current_depth = hi[j] - leg.end_price
                if hi[j] > deepest_so_far_price:
                    deepest_so_far_price = hi[j]
                depth_from_deepest = deepest_so_far_price - leg.end_price

            max_depth = max(max_depth, current_depth)

            # Step 1: check qualification
            if not qualified and max_depth >= threshold:
                qualified = True
                qual_i = j

            if not qualified:
                continue

            # Step 2: check turn evidence (CAUSAL — uses only this bar and past)
            depth_atr = depth_from_deepest / bar_a
            depth_pct = depth_from_deepest / leg.distance if leg.distance > 0 else 0
            bars_in_pb = j - leg.end_i
            body = cl[j] - op[j]
            body_abs = abs(body)
            bar_range = hi[j] - lo[j]

            found_turn = None

            # T1: close reversal — close is back toward leg direction vs prior close
            if j > leg.end_i + 1:
                if leg.direction == "BULL" and cl[j] > cl[j - 1] and body > 0:
                    found_turn = TurnType.T1_CLOSE_REVERSAL
                elif leg.direction == "BEAR" and cl[j] < cl[j - 1] and body < 0:
                    found_turn = TurnType.T1_CLOSE_REVERSAL

            # T2: body reversal — substantial body in leg direction
            if found_turn is None and body_abs / bar_a >= body_threshold_atr:
                if (leg.direction == "BULL" and body > 0) or (leg.direction == "BEAR" and body < 0):
                    found_turn = TurnType.T2_BODY_REVERSAL

            # T3: wick rejection — wick into pullback zone with close back
            if found_turn is None and bar_range > 0:
                if leg.direction == "BULL":
                    lower_wick = cl[j] - lo[j] if cl[j] > op[j] else op[j] - lo[j]
                    if lower_wick / bar_range >= wick_threshold_pct and cl[j] > op[j]:
                        found_turn = TurnType.T3_WICK_REJECTION
                else:
                    upper_wick = hi[j] - cl[j] if cl[j] < op[j] else hi[j] - op[j]
                    if upper_wick / bar_range >= wick_threshold_pct and cl[j] < op[j]:
                        found_turn = TurnType.T3_WICK_REJECTION

            if found_turn is not None:
                counter += 1
                turns.append(CausalTurn(
                    turn_type=found_turn,
                    leg=leg,
                    qualification_i=qual_i,
                    turn_i=j,
                    entry_i=j,
                    direction=trade_dir,
                    leg_distance_atr=leg.distance_atr,
                    pullback_depth_at_turn=depth_atr,
                    pullback_depth_pct=depth_pct,
                    bars_in_pullback=bars_in_pb,
                    turn_id=f"CT-{counter:07d}",
                ))
                break  # one turn per leg

    return turns


def turns_to_df(turns: list[CausalTurn]) -> pd.DataFrame:
    return pd.DataFrame([{
        "turn_id": t.turn_id,
        "turn_type": t.turn_type.value,
        "direction": t.direction,
        "leg_id": t.leg.leg_id,
        "qualification_i": t.qualification_i,
        "turn_i": t.turn_i,
        "entry_i": t.entry_i,
        "leg_distance_atr": t.leg_distance_atr,
        "pullback_depth_at_turn": t.pullback_depth_at_turn,
        "pullback_depth_pct": t.pullback_depth_pct,
        "bars_in_pullback": t.bars_in_pullback,
        "timestamp_ct": t.leg.end_ts,
    } for t in turns])
