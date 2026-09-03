"""Stop placement variants for Phase 48."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TARGET_R_CONT, TARGET_R_REV
from .structure import causal_swing_levels


def compute_stop(
    market: pd.DataFrame,
    entry_i: int,
    entry_price: float,
    direction: str,
    signal_type: str,
    *,
    mode: str,
    frozen_stop: float,
    bos_level: float | None = None,
    atr_mult: float = 0.75,
    buffer_atr: float = 0.25,
    hybrid_min_atr: float = 0.5,
    hybrid_max_atr: float = 1.5,
) -> tuple[float, float]:
    """Return (stop_price, target_price) normalized to 1R with fixed R target."""
    d = 1 if str(direction).lower() == "long" else -1
    atr = float(market.iloc[entry_i].get("atr", np.nan))
    if not np.isfinite(atr) or atr <= 0:
        atr = abs(entry_price - frozen_stop) or 1.0
    tgt_r = TARGET_R_CONT if signal_type in ("L", "S") else TARGET_R_REV
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values

    if mode == "S0":
        return float(frozen_stop), entry_price + d * tgt_r * abs(entry_price - frozen_stop)

    if mode == "S1":
        sh, sl, _, _ = causal_swing_levels(hi, lo, entry_i)
        stop = (sl - 0.25) if d == 1 and np.isfinite(sl) else (sh + 0.25) if np.isfinite(sh) else frozen_stop
        if d == 1:
            stop = min(stop, entry_price - 0.25)
        else:
            stop = max(stop, entry_price + 0.25)
        risk = abs(entry_price - stop) or 1e-9
        return stop, entry_price + d * tgt_r * risk

    if mode == "S2":
        level = bos_level if bos_level is not None and np.isfinite(bos_level) else frozen_stop
        stop = level - buffer_atr * atr if d == 1 else level + buffer_atr * atr
        risk = abs(entry_price - stop) or 1e-9
        return stop, entry_price + d * tgt_r * risk

    if mode == "S3":
        stop = entry_price - atr_mult * atr if d == 1 else entry_price + atr_mult * atr
        risk = abs(entry_price - stop) or 1e-9
        return stop, entry_price + d * tgt_r * risk

    if mode == "S4":
        sh, sl, _, _ = causal_swing_levels(hi, lo, entry_i)
        struct_stop = (sl - buffer_atr * atr) if d == 1 and np.isfinite(sl) else (sh + buffer_atr * atr) if np.isfinite(sh) else frozen_stop
        atr_stop = entry_price - hybrid_min_atr * atr if d == 1 else entry_price + hybrid_min_atr * atr
        if d == 1:
            stop = max(struct_stop, entry_price - hybrid_max_atr * atr)
            stop = min(stop, entry_price - hybrid_min_atr * atr)
        else:
            stop = min(struct_stop, entry_price + hybrid_max_atr * atr)
            stop = max(stop, entry_price + hybrid_min_atr * atr)
        risk = abs(entry_price - stop) or 1e-9
        return stop, entry_price + d * tgt_r * risk

    return float(frozen_stop), entry_price + d * tgt_r * abs(entry_price - frozen_stop)


def structure_target_price(market: pd.DataFrame, entry_i: int, entry_price: float, direction: str, risk: float) -> float | None:
    d = 1 if str(direction).lower() == "long" else -1
    hi = market["high"].astype(float).values
    lo = market["low"].astype(float).values
    sh, sl, _, _ = causal_swing_levels(hi, lo, entry_i)
    if d == 1 and np.isfinite(sh) and sh > entry_price:
        return float(sh)
    if d == -1 and np.isfinite(sl) and sl < entry_price:
        return float(sl)
    return None
