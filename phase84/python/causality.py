"""Causality audit — truncation invariance at decision time."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase84.python.features import compute_features_at_signal
from phase84.python.state_machine import apply_variant


def truncation_test(
    m1: pd.DataFrame,
    signals: pd.DataFrame,
    sample: int = 500,
    variant: str = "E3",
) -> dict:
    hi = m1["high"].values.astype(float)
    lo = m1["low"].values.astype(float)
    cl = m1["close"].values.astype(float)
    op = m1["open"].values.astype(float)
    atr = m1["atr"].values.astype(float) if "atr" in m1.columns else (hi - lo)

    rng = np.random.default_rng(42)
    idxs = signals.index.tolist()
    if len(idxs) > sample:
        idxs = rng.choice(idxs, size=sample, replace=False).tolist()

    mismatches = 0
    tested = 0
    for ix in idxs:
        row = signals.loc[ix]
        si = int(row["signal_i"])
        if si < 25 or si >= len(cl) - 5:
            continue
        full = compute_features_at_signal(hi, lo, cl, op, atr, si, row["phase72a_direction"])
        trunc_hi, trunc_lo = hi[: si + 1], lo[: si + 1]
        trunc_cl, trunc_op = cl[: si + 1], op[: si + 1]
        trunc_atr = atr[: si + 1]
        part = compute_features_at_signal(trunc_hi, trunc_lo, trunc_cl, trunc_op, trunc_atr, si, row["phase72a_direction"])

        for k in ("range_position_20", "move_5m_ATR", "failed_break", "break_close_accept"):
            if full.get(k) != part.get(k):
                if isinstance(full.get(k), float) and isinstance(part.get(k), float):
                    if abs(full[k] - part[k]) > 1e-9:
                        mismatches += 1
                        break
                else:
                    mismatches += 1
                    break

        d_full = apply_variant({**row.to_dict(), **full}, variant)
        d_part = apply_variant({**row.to_dict(), **part}, variant)
        if d_full.decision != d_part.decision:
            mismatches += 1
        tested += 1

    return {
        "tested": tested,
        "mismatches": mismatches,
        "pass": mismatches == 0,
    }
