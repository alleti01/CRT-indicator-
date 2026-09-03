"""Leg1 → Pullback → Leg2 sequences: continuation and reversal detection.

C1 = continuation: Leg 1 with existing trend → pullback → potential Leg 2
R1 = reversal: opposing Leg 1 → pullback → retest → potential reversal Leg 2
Failed setups are classified separately.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from phase57.research.legs import PriceLeg
from phase57.research.pullbacks import Pullback


@dataclass
class Sequence:
    seq_type: str           # "C1" (continuation) or "R1" (reversal)
    leg1: PriceLeg
    pullback: Pullback
    direction: str          # expected Leg 2 direction (same as Leg 1)
    setup_i: int            # bar where setup is complete (pullback deepest)
    setup_ts: pd.Timestamp
    reaction_i: int | None  # first bar showing directional reaction
    reaction_strength: float  # first reaction bar body / ATR
    failed: bool            # did the setup fail (opposite continuation)
    seq_id: str = ""


def detect_sequences(
    m1: pd.DataFrame,
    legs: list[PriceLeg],
    pullbacks: list[Pullback],
    *,
    max_reaction_bars: int = 5,
) -> list[Sequence]:
    """Detect Leg1 → Pullback → reaction sequences.

    Continuation (C1): Leg 1 extends existing directional trend.
    Reversal (R1): Leg 1 opposes prior directional context.
    """
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float)
    idx = m1.index
    n = len(m1)
    sequences: list[Sequence] = []
    counter = 0

    # Build a simple directional context: was the prior leg same or opposite?
    leg_by_end = {}
    for lg in legs:
        leg_by_end[lg.end_i] = lg

    for pb in pullbacks:
        leg = pb.leg
        if pb.deepest_i + 1 >= n:
            continue

        # Determine C1 vs R1: look for a prior leg in opposite direction
        prior_legs = [l for l in legs if l.end_i < leg.start_i and l.end_i > leg.start_i - 200]
        if prior_legs:
            last_prior = max(prior_legs, key=lambda l: l.end_i)
            if last_prior.direction != leg.direction:
                seq_type = "R1"  # reversal: prior was opposite
            else:
                seq_type = "C1"  # continuation: prior was same
        else:
            seq_type = "C1"  # no prior context → treat as continuation

        setup_i = pb.deepest_i
        a = atr[setup_i] if np.isfinite(atr[setup_i]) else 1.0

        # Look for reaction in first few bars after pullback deepest point
        reaction_i = None
        reaction_strength = 0.0
        failed = False
        end = min(n, setup_i + 1 + max_reaction_bars)
        for j in range(setup_i + 1, end):
            body = cl[j] - op[j]
            body_norm = body / a if a > 0 else 0.0
            if leg.direction == "BULL" and body > 0:
                reaction_i = j
                reaction_strength = abs(body_norm)
                break
            elif leg.direction == "BEAR" and body < 0:
                reaction_i = j
                reaction_strength = abs(body_norm)
                break
            # Opposite body = potential failure signal
            if leg.direction == "BULL" and body < 0 and abs(body_norm) > 0.3:
                failed = True
            elif leg.direction == "BEAR" and body > 0 and abs(body_norm) > 0.3:
                failed = True

        if reaction_i is None:
            failed = True

        counter += 1
        sequences.append(Sequence(
            seq_type=seq_type,
            leg1=leg,
            pullback=pb,
            direction=leg.direction,
            setup_i=setup_i,
            setup_ts=idx[setup_i],
            reaction_i=reaction_i,
            reaction_strength=reaction_strength,
            failed=failed,
            seq_id=f"SEQ-{counter:07d}",
        ))
    return sequences


def sequences_to_df(sequences: list[Sequence]) -> pd.DataFrame:
    return pd.DataFrame([{
        "seq_id": s.seq_id,
        "seq_type": s.seq_type,
        "direction": s.direction,
        "leg_id": s.leg1.leg_id,
        "pullback_id": s.pullback.pullback_id,
        "setup_i": s.setup_i,
        "setup_ts": s.setup_ts,
        "reaction_i": s.reaction_i,
        "reaction_strength": s.reaction_strength,
        "failed": s.failed,
        "leg_distance_atr": s.leg1.distance_atr,
        "pullback_depth_pct": s.pullback.depth_pct_of_leg,
        "prior_swing_holds": s.pullback.prior_swing_holds,
    } for s in sequences])
