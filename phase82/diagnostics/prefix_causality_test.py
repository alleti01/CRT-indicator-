#!/usr/bin/env python3
"""Phase82 prefix causality test — 15M-only, 500+ timestamps."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_market_1m_lw
from phase82.python.m15_causal import build_m15_causal_arrays, _bucket_start, _is_bucket_close
from phase82.python.m15_state import m15_state_at


def _manual_dev_at(m1: pd.DataFrame, i: int) -> dict:
    """Recompute developing 15M OHLC from 1M bars up to i only (causal)."""
    ts = m1.index[i]
    b = _bucket_start(ts)
    mask = (m1.index >= b) & (m1.index <= ts)
    sub = m1.loc[mask]
    return {
        "o": float(sub["open"].iloc[0]),
        "h": float(sub["high"].max()),
        "l": float(sub["low"].min()),
        "c": float(sub["close"].iloc[-1]),
    }


def _completed_label(ts: pd.Timestamp) -> pd.Timestamp:
    b = _bucket_start(ts)
    if _is_bucket_close(ts):
        return b
    return b - pd.Timedelta(minutes=15)


def run_prefix_test(n_sample: int = 500, seed: int = 42) -> dict:
    m1 = load_market_1m_lw()
    arr = build_m15_causal_arrays(m1)
    n = arr.n
    rng = np.random.default_rng(seed)

    # Stratified indices across years and sessions
    years = m1.index.year.values
    idx_pool: list[int] = []
    for y in np.unique(years):
        ys = np.where(years == y)[0]
        idx_pool.extend(rng.choice(ys, size=min(55, len(ys)), replace=False).tolist())
    idx_pool = list(dict.fromkeys([i for i in idx_pool if 30 <= i < n - 30]))[:n_sample]
    if len(idx_pool) < n_sample:
        extra = rng.choice(np.arange(30, n - 30), size=n_sample - len(idx_pool), replace=False)
        idx_pool.extend(int(x) for x in extra)
    idx_pool = idx_pool[:n_sample]

    failures = []

    for i in idx_pool:
        manual = _manual_dev_at(m1, i)
        if abs(manual["c"] - arr.m15_dev_cl[i]) > 1e-4:
            failures.append({"i": i, "field": "dev_cl", "arr": float(arr.m15_dev_cl[i]), "manual": manual["c"]})
        if abs(manual["h"] - arr.m15_dev_hi[i]) > 1e-4:
            failures.append({"i": i, "field": "dev_hi", "arr": float(arr.m15_dev_hi[i]), "manual": manual["h"]})

    # Truncated prefix on small recent window only (fast, 30 checks)
    tail_start = max(30, n - 5_000)
    trunc_pool = [int(x) for x in rng.choice(np.arange(tail_start, n - 30), size=min(30, n - tail_start - 30), replace=False)]
    for i in trunc_pool:
        full_state = m15_state_at(arr, i)["m15_state"]
        sub = m1.iloc[: i + 1]
        arr_sub = build_m15_causal_arrays(sub)
        trunc_state = m15_state_at(arr_sub, arr_sub.n - 1)["m15_state"]
        if trunc_state != full_state:
            failures.append({"i": i, "field": "m15_state", "full": full_state, "trunc": trunc_state})

    return {
        "sampled": len(idx_pool),
        "trunc_state_checks": len(trunc_pool),
        "failures": len(failures),
        "pass": len(failures) == 0,
        "detail": failures[:15],
    }


if __name__ == "__main__":
    r = run_prefix_test()
    print(r)
    raise SystemExit(0 if r["pass"] else 1)
