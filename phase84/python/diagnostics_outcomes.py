"""Diagnostic-only forward outcomes (MFE/MAE) — never used in decisions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase84.python.config import OUTCOME_HORIZONS


def horizon_mfe_mae(
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    entry_i: int,
    direction: str,
    risk: float,
    horizons: tuple[int, ...] = OUTCOME_HORIZONS,
) -> dict:
    d = 1 if direction == "LONG" else -1
    ep = float(cl[entry_i])
    risk = max(risk, 1e-9)
    out: dict = {}
    n = len(cl)
    for h in horizons:
        end = min(entry_i + h, n - 1)
        seg_hi = hi[entry_i : end + 1]
        seg_lo = lo[entry_i : end + 1]
        if d == 1:
            mfe = (float(np.max(seg_hi)) - ep) / risk
            mae = (ep - float(np.min(seg_lo))) / risk
        else:
            mfe = (ep - float(np.min(seg_lo))) / risk
            mae = (float(np.max(seg_hi)) - ep) / risk
        out[f"MFE_{h}m"] = mfe
        out[f"MAE_{h}m"] = mae
    return out


def attach_diagnostic_outcomes(trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    atr = m1["atr"].values.astype(float) if "atr" in m1.columns else (hi - lo)

    rows = []
    for _, t in trades.iterrows():
        ei = int(t["entry_i"])
        direction = t["phase72a_direction"]
        atr_t = float(t.get("atr_signal", atr[ei]))
        risk = atr_t * 1.0
        diag = horizon_mfe_mae(hi, lo, cl, ei, direction, risk)
        rows.append({**t.to_dict(), **diag})
    return pd.DataFrame(rows)
