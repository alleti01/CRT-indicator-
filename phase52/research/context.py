"""15M context families C0–C5 for S52 (causal)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.config import DISPLACEMENT_BODY_MULT, RANGE_LOOKBACK_15M
from phase52.research.swings import causal_swing_high, causal_swing_low, recent_swing_highs, recent_swing_lows


def context_allows(ctx: str, direction: int, i: int, m15: pd.DataFrame, m15_i: int) -> bool:
    if ctx == "C0":
        return True
    if m15_i < 0 or m15_i >= len(m15):
        return False
    row = m15.iloc[m15_i]
    hi = m15["high"].values[: m15_i + 1]
    lo = m15["low"].values[: m15_i + 1]
    cl = m15["close"].values[: m15_i + 1]
    op = m15["open"].values[: m15_i + 1]
    atr = float(row.get("atr", np.nan))
    if ctx == "C1":
        sh = recent_swing_highs(hi, m15_i, 2)
        sl = recent_swing_lows(lo, m15_i, 2)
        if direction == 1 and len(sh) >= 2 and len(sl) >= 2:
            return sh[0][1] > sh[1][1] and sl[0][1] > sl[1][1]
        if direction == -1 and len(sh) >= 2 and len(sl) >= 2:
            return sh[0][1] < sh[1][1] and sl[0][1] < sl[1][1]
        return False
    if ctx == "C2":
        if m15_i < 4 or not np.isfinite(atr) or atr <= 0:
            return False
        mom = (cl[m15_i] - cl[m15_i - 4]) / atr
        return mom >= 0.5 if direction == 1 else mom <= -0.5
    if ctx == "C3":
        body = abs(cl[m15_i] - op[m15_i])
        if m15_i < 20:
            return False
        avg = np.mean(np.abs(cl[m15_i - 19 : m15_i + 1] - op[m15_i - 19 : m15_i + 1]))
        return body > DISPLACEMENT_BODY_MULT * avg
    if ctx == "C4":
        lb = min(RANGE_LOOKBACK_15M, m15_i + 1)
        rh = np.max(hi[m15_i - lb + 1 : m15_i + 1])
        rl = np.min(lo[m15_i - lb + 1 : m15_i + 1])
        rng = rh - rl
        if rng <= 0:
            return False
        loc = (cl[m15_i] - rl) / rng
        return loc >= 0.66 if direction == 1 else loc <= 0.34
    if ctx == "C5":
        if m15_i < 3:
            return False
        ups = sum(cl[m15_i - k] > cl[m15_i - k - 1] for k in range(3))
        return ups >= 2 if direction == 1 else ups <= 1
    return True
