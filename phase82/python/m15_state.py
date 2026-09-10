"""Causal 15M market state labels (context only, not prediction)."""
from __future__ import annotations

import numpy as np

from phase82.python.m15_causal import M15CausalArrays

STATES = (
    "15M_BULLISH",
    "15M_BEARISH",
    "15M_NEUTRAL",
    "15M_TRANSITION_UP",
    "15M_TRANSITION_DOWN",
    "15M_EXTENDED_UP",
    "15M_EXTENDED_DOWN",
    "15M_BALANCED",
)


def m15_state_at(arr: M15CausalArrays, i: int, ext_atr: float = 1.0) -> dict:
    """Causal 15M context at 1M bar i (decision at bar close i)."""
    cj = int(arr.m15_completed_j[i])
    atr = float(arr.atr[i]) if arr.atr[i] > 0 else 1.0
    m15_atr = float(arr.m15_native_atr[cj]) if cj >= 0 and arr.m15_native_atr[cj] > 0 else atr

    dev_op = float(arr.m15_dev_op[i])
    dev_cl = float(arr.m15_dev_cl[i])
    dev_hi = float(arr.m15_dev_hi[i])
    dev_lo = float(arr.m15_dev_lo[i])

    dev_disp = (dev_cl - dev_op) / m15_atr
    dev_range = (dev_hi - dev_lo) / m15_atr

    comp_bull = comp_bear = False
    comp_cl = comp_hi = comp_lo = np.nan
    if cj >= 2:
        c0, c1, c2 = arr.m15_native_cl[cj], arr.m15_native_cl[cj - 1], arr.m15_native_cl[cj - 2]
        h1, h2 = arr.m15_native_hi[cj - 1], arr.m15_native_hi[cj - 2]
        l1, l2 = arr.m15_native_lo[cj - 1], arr.m15_native_lo[cj - 2]
        comp_cl = float(c0)
        comp_bull = c1 > c2 and h1 > h2
        comp_bear = c1 < c2 and l1 < l2
    elif cj >= 1:
        comp_cl = float(arr.m15_native_cl[cj])
        comp_bull = arr.m15_native_cl[cj] > arr.m15_native_cl[cj - 1]
        comp_bear = arr.m15_native_cl[cj] < arr.m15_native_cl[cj - 1]

    move_from_comp = (dev_cl - comp_cl) / m15_atr if np.isfinite(comp_cl) else 0.0
    loc_in_range = 0.5
    if cj >= 0:
        rh = float(arr.m15_native_hi[cj])
        rl = float(arr.m15_native_lo[cj])
        if rh > rl:
            loc_in_range = (dev_cl - rl) / (rh - rl)

    extended_up = move_from_comp >= ext_atr and dev_cl >= dev_hi - 0.15 * (dev_hi - dev_lo + 1e-9)
    extended_down = move_from_comp <= -ext_atr and dev_cl <= dev_lo + 0.15 * (dev_hi - dev_lo + 1e-9)
    balanced = dev_range < 0.5 and abs(dev_disp) < 0.3

    state = "15M_NEUTRAL"
    if extended_up:
        state = "15M_EXTENDED_UP"
    elif extended_down:
        state = "15M_EXTENDED_DOWN"
    elif balanced:
        state = "15M_BALANCED"
    elif comp_bull and dev_disp > 0:
        state = "15M_BULLISH"
    elif comp_bear and dev_disp < 0:
        state = "15M_BEARISH"
    elif comp_bear and dev_disp > 0.2:
        state = "15M_TRANSITION_UP"
    elif comp_bull and dev_disp < -0.2:
        state = "15M_TRANSITION_DOWN"
    elif comp_bull:
        state = "15M_BULLISH"
    elif comp_bear:
        state = "15M_BEARISH"

    return {
        "m15_state": state,
        "m15_extension_atr": move_from_comp,
        "m15_dev_disp": dev_disp,
        "m15_dev_range_atr": dev_range,
        "m15_loc_in_range": loc_in_range,
        "m15_comp_bull": comp_bull,
        "m15_comp_bear": comp_bear,
        "known_at": arr.idx[i],
        "source_ts": arr.idx[i],
    }


def precompute_m15_states(arr: M15CausalArrays, ext_atr: float = 1.0) -> dict[str, np.ndarray]:
    """Vectorized-ish precompute for all bars."""
    n = arr.n
    states = np.empty(n, dtype=object)
    ext = np.zeros(n)
    disp = np.zeros(n)
    for i in range(n):
        s = m15_state_at(arr, i, ext_atr)
        states[i] = s["m15_state"]
        ext[i] = s["m15_extension_atr"]
        disp[i] = s["m15_dev_disp"]
    return {"m15_state": states, "m15_extension_atr": ext, "m15_dev_disp": disp}
