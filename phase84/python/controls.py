"""Mandatory control experiments."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase84.python.metrics import random_pass_control, summarize_r


def random_pass_benchmark(df: pd.DataFrame, candidate_mask: pd.Series, r_col: str = "net_R") -> dict:
    rand = random_pass_control(df, candidate_mask)
    return {
        "candidate": summarize_r(df[candidate_mask], r_col),
        "random_pass": summarize_r(df[rand], r_col),
        "baseline_all": summarize_r(df, r_col),
    }


def random_wait_benchmark(
    df: pd.DataFrame,
    delay_col: str = "entry_delay_bars",
    r_col: str = "net_R",
    seed: int = 42,
) -> dict:
    """Compare intentional wait delays vs random delay assignment."""
    waited = df.loc[df[delay_col] > 0]
    if waited.empty:
        return {"N": 0}
    rng = np.random.default_rng(seed)
    random_delays = rng.integers(1, 4, size=len(waited))
    return {
        "wait_intentional_N": len(waited),
        "wait_intentional_AvgR": float(waited[r_col].mean()),
        "random_delay_note": "Assign random 1-3 bar delays for same subset in extended runner",
    }
