"""Prefix invariance audit for Phase77 features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CAUSALITY_ATOL, CAUSALITY_RTOL


def compare_prefix(full: pd.DataFrame, prefix: pd.DataFrame, cols: list[str]) -> dict:
    results = {}
    common = prefix.index.intersection(full.index)
    for col in cols:
        if col not in full.columns:
            continue
        a = prefix.loc[common, col]
        b = full.loc[common, col]
        if a.dtype == object or b.dtype == object:
            match = (a.astype(str) == b.astype(str)).mean()
            results[col] = {"match_rate": float(match), "pass": match >= 0.999}
        else:
            ok = np.allclose(a.astype(float), b.astype(float), rtol=CAUSALITY_RTOL, atol=CAUSALITY_ATOL, equal_nan=True)
            results[col] = {"pass": bool(ok)}
    passed = sum(1 for v in results.values() if v.get("pass"))
    return {"columns": results, "passed": passed, "total": len(results), "status": "PASS" if passed == len(results) else "FAIL"}


def causality_audit(feat: pd.DataFrame, *, cutoffs=(0.25, 0.50, 0.75)) -> dict:
    cols = [
        "dev_poc", "dev_vah", "dev_val", "auction_state", "location_type",
        "structure_state", "price_response", "confirmation_state",
    ]
    out = {}
    n = len(feat)
    for frac in cutoffs:
        end = int(n * frac)
        pref = feat.iloc[:end]
        recomputed_end = pref.index[-1]
        full_slice = feat.loc[:recomputed_end]
        out[str(frac)] = compare_prefix(full_slice, pref, cols)
    all_pass = all(v["status"] == "PASS" for v in out.values())
    return {"cutoffs": out, "status": "CAUSALITY_PASS" if all_pass else "CAUSALITY_FAIL"}
