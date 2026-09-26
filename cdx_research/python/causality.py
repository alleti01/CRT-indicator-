"""Truncate-at-T vs full-history causality check for reconstructed features/rules."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cdx_research.python.features import add_causal_features
from cdx_research.python.rules import apply_candidate_v1


COMPARE_COLS = [
    "atr14",
    "rsi_14",
    "ema_21",
    "near_low_20",
    "near_high_20",
    "close_through_high_20",
    "lower_wick_frac",
]


def run_causality(m1: pd.DataFrame, sample_n: int = 500, seed: int = 7) -> dict:
    full = add_causal_features(m1)
    full_sig = apply_candidate_v1(full)
    usable = np.where(full["atr14"].notna().to_numpy())[0]
    usable = usable[usable >= 250]
    usable = usable[usable < len(full) - 5]
    if len(usable) == 0:
        return {"status": "FAIL", "reason": "no usable bars"}
    rng = np.random.default_rng(seed)
    take = rng.choice(usable, size=min(sample_n, len(usable)), replace=False)
    mismatches = []
    for idx in take:
        trunc = add_causal_features(m1.iloc[: idx + 1])
        for col in COMPARE_COLS:
            a = trunc[col].iloc[-1]
            b = full[col].iloc[idx]
            if pd.isna(a) and pd.isna(b):
                continue
            if pd.isna(a) or pd.isna(b) or not np.isclose(float(a), float(b), rtol=0, atol=1e-9):
                mismatches.append({"i": int(idx), "col": col, "trunc": a, "full": b})
                break
        if apply_candidate_v1(trunc).iloc[-1] != full_sig.iloc[idx]:
            mismatches.append({"i": int(idx), "col": "candidate_v1", "trunc": int(apply_candidate_v1(trunc).iloc[-1]), "full": int(full_sig.iloc[idx])})
    status = "PASS" if not mismatches else "FAIL"
    return {
        "status": status,
        "sampled": int(len(take)),
        "mismatches": len(mismatches),
        "examples": mismatches[:8],
        "verdict": "PASS" if status == "PASS" else "CDX_RE_CAUSALITY_FAIL",
    }
