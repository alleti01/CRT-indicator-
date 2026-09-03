"""Pine f_atrUse — SMA range fallback semantics."""
from __future__ import annotations

import numpy as np


def sma_range_atr(high: np.ndarray, low: np.ndarray, period: int = 14) -> np.ndarray:
    rng = high - low
    out = np.full(len(rng), np.nan, dtype=float)
    if len(rng) < period:
        return out
    cs = np.cumsum(np.nan_to_num(rng, nan=0.0))
    out[period - 1 :] = (cs[period - 1 :] - np.concatenate([[0.0], cs[:-period]])) / period
    return out


def atr_use(raw: np.ndarray) -> np.ndarray:
    """Vectorized Pine f_atrUse(raw)."""
    n = len(raw)
    out = raw.copy().astype(float)
    for i in range(n):
        v = out[i]
        if not np.isfinite(v) or v <= 0:
            v = raw[i - 1] if i > 0 and np.isfinite(raw[i - 1]) else 0.0
        if v <= 0:
            for k in range(2, 6):
                if i - k >= 0:
                    bk = raw[i - k]
                    if np.isfinite(bk) and bk > 0:
                        v = bk
                        break
        out[i] = 1.0 if (not np.isfinite(v) or v <= 0) else float(v)
    return out
