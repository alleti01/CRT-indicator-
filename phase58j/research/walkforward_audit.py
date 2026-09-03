"""Walk-forward and overlap audits."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.simulation import metrics


def overlap_stats(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    events = []
    for _, t in trades.iterrows():
        events.append((int(t["entry_i"]), 1))
        events.append((int(t["exit_i"]), -1))
    events.sort()
    cur = mx = 0
    for _, d in events:
        cur += d
        mx = max(mx, cur)
    # concurrent at each entry
    conc = []
    for _, t in trades.iterrows():
        ei, ex = int(t["entry_i"]), int(t["exit_i"])
        c = ((trades["entry_i"] < ex) & (trades["exit_i"] > ei)).sum()
        conc.append(c)
    return {
        "max_concurrent": int(mx),
        "median_concurrent": float(np.median(conc)),
        "p95_concurrent": float(np.percentile(conc, 95)),
        "overlapping_pairs": int(sum(c > 1 for c in conc)),
    }


def walkforward_splits(n: int, train_frac: float, valid_frac: float) -> dict:
    te = int(n * train_frac)
    ve = int(n * valid_frac)
    return {"train": (0, te), "validation": (te, ve), "holdout": (ve, n)}


def split_metrics(trades: pd.DataFrame, splits: dict, r_col: str = "net_R") -> pd.DataFrame:
    rows = []
    for name, (a, b) in splits.items():
        sub = trades.iloc[a:b]
        m = metrics(sub[r_col].values)
        rows.append({"split": name, **m})
    return pd.DataFrame(rows)
