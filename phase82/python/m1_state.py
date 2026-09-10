"""Causal 1M execution features and state machine inputs."""
from __future__ import annotations

import numpy as np

from phase82.python.m15_causal import M15CausalArrays

M1_STATES = (
    "NEUTRAL",
    "WATCH_LONG",
    "WATCH_SHORT",
    "PULLBACK_LONG",
    "PULLBACK_SHORT",
    "REACTION_LONG",
    "REACTION_SHORT",
    "LONG_READY",
    "SHORT_READY",
)


def m1_features_at(arr: M15CausalArrays, i: int, lookback: int = 10) -> dict:
    """Causal 1M execution context at bar i."""
    if i < lookback + 1:
        return {}
    hi, lo, cl, op, atr = arr.hi, arr.lo, arr.cl, arr.op, arr.atr
    a = float(atr[i]) if atr[i] > 0 else 1.0
    lb = max(0, i - lookback)

    roll_hi = float(np.max(hi[lb:i]))
    roll_lo = float(np.min(lo[lb:i]))
    body = float(cl[i] - op[i])
    rng = float(hi[i] - lo[i]) if hi[i] > lo[i] else 1e-9
    bull = body > 0
    bear = body < 0
    body_atr = abs(body) / a
    close_loc = (cl[i] - lo[i]) / rng

    move_up = (cl[i] - roll_lo) / a
    move_down = (roll_hi - cl[i]) / a
    ext_up = move_up >= 1.0
    ext_down = move_down >= 1.0

    # Pullback: retrace from local extreme in last 5 bars
    lh = float(np.max(hi[i - 5 : i + 1]))
    ll = float(np.min(lo[i - 5 : i + 1]))
    pullback_from_high = (lh - cl[i]) / a
    pullback_from_low = (cl[i] - ll) / a

    micro_bos_up = cl[i] > float(np.max(hi[lb:i]))
    micro_bos_down = cl[i] < float(np.min(lo[lb:i]))

    commitment_long = bull and body_atr >= 0.4 and close_loc >= 0.6
    commitment_short = bear and body_atr >= 0.4 and close_loc <= 0.4
    reaction_long = bull and pullback_from_high >= 0.25
    reaction_short = bear and pullback_from_low >= 0.25

    m1_state = "NEUTRAL"
    if commitment_long:
        m1_state = "LONG_READY"
    elif commitment_short:
        m1_state = "SHORT_READY"
    elif reaction_long:
        m1_state = "REACTION_LONG"
    elif reaction_short:
        m1_state = "REACTION_SHORT"
    elif pullback_from_high >= 0.25:
        m1_state = "PULLBACK_LONG"
    elif pullback_from_low >= 0.25:
        m1_state = "PULLBACK_SHORT"
    elif move_up > move_down and move_up > 0.3:
        m1_state = "WATCH_LONG"
    elif move_down > move_up and move_down > 0.3:
        m1_state = "WATCH_SHORT"

    return {
        "m1_state": m1_state,
        "m1_body_atr": body_atr,
        "m1_extension_up_atr": move_up,
        "m1_extension_down_atr": move_down,
        "m1_ext_up": ext_up,
        "m1_ext_down": ext_down,
        "pullback_from_high_atr": pullback_from_high,
        "pullback_from_low_atr": pullback_from_low,
        "commitment_long": commitment_long,
        "commitment_short": commitment_short,
        "reaction_long": reaction_long,
        "reaction_short": reaction_short,
        "micro_bos_up": micro_bos_up,
        "micro_bos_down": micro_bos_down,
        "known_at": arr.idx[i],
    }


def scan_reset_entry(
    arr: M15CausalArrays,
    start_i: int,
    direction: str,
    max_bars: int = 30,
    pullback_atr: float = 0.35,
) -> tuple[int | None, str]:
    """After WAIT, scan forward for pullback → reaction → commitment. Return entry bar index."""
    for j in range(start_i + 1, min(start_i + max_bars + 1, arr.n - 2)):
        f = m1_features_at(arr, j)
        if not f:
            continue
        if direction == "LONG":
            if f["pullback_from_high_atr"] >= pullback_atr and f["reaction_long"] and f["commitment_long"]:
                return j + 1, "RESET_LONG"
            if f["commitment_long"] and f["pullback_from_high_atr"] >= pullback_atr * 0.5:
                return j + 1, "RESET_LONG"
        else:
            if f["pullback_from_low_atr"] >= pullback_atr and f["reaction_short"] and f["commitment_short"]:
                return j + 1, "RESET_SHORT"
            if f["commitment_short"] and f["pullback_from_low_atr"] >= pullback_atr * 0.5:
                return j + 1, "RESET_SHORT"
    return None, "PASS_NO_RESET"
