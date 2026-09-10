"""Evaluate M0 outcomes on entry subsets."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_subset(df: pd.DataFrame, mask: pd.Series | None = None, *, r_col: str = "net_R_m1") -> dict:
    sub = df[mask] if mask is not None else df
    rs = sub[r_col].astype(float).values
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    eq = np.cumsum(rs)
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    gross = sub.loc[mask, "gross_R_m1"].astype(float).values if mask is not None else sub["gross_R_m1"].astype(float).values
    gross = gross[np.isfinite(gross)]
    out = {
        "N": int(len(rs)),
        "WinRate": float((rs > 0).mean()),
        "AvgR": float(rs.mean()),
        "PF": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf"),
        "TotalR": float(rs.sum()),
        "MaxDD": float((np.maximum.accumulate(eq) - eq).max()),
        "MedianR": float(np.median(rs)),
        "GrossAvgR": float(gross.mean()) if len(gross) else 0.0,
        "GrossTotalR": float(gross.sum()) if len(gross) else 0.0,
    }
    if "direction_m1" in sub.columns and len(rs) > 0:
        for d in ("LONG", "SHORT"):
            m = sub.loc[mask, "direction_m1"] == d if mask is not None else sub["direction_m1"] == d
            rsd = sub.loc[m, r_col].astype(float)
            out[f"{d}_AvgR"] = float(rsd.mean()) if len(rsd) else 0.0
            out[f"{d}_N"] = int(len(rsd))
    return out


def kept_vs_rejected(df: pd.DataFrame, mask: pd.Series) -> dict:
    kept = summarize_subset(df, mask)
    rejected = summarize_subset(df, ~mask)
    return {"kept": kept, "rejected": rejected}


def random_direction_proxy(df: pd.DataFrame, mask: pd.Series) -> dict:
    """Deterministic sign-flip control — same entries, randomized direction edge null."""
    sub = df[mask].copy()
    if len(sub) == 0:
        return {"N": 0, "AvgR_real": 0.0, "AvgR_random": 0.0}
    rng = np.random.default_rng(42)
    flip = rng.choice([-1, 1], size=len(sub))
    real = sub["net_R_m1"].astype(float).mean()
    random_r = (sub["gross_R_m1"].astype(float) * flip - sub["cost_R_m1"].astype(float)).mean()
    return {"N": len(sub), "AvgR_real": float(real), "AvgR_random": float(random_r), "directional_lift": float(real - random_r)}


def year_stability(df: pd.DataFrame, mask: pd.Series) -> float:
    sub = df[mask].copy()
    sub["year"] = sub["entry_ts"].dt.year
    base = df.copy()
    base["year"] = base["entry_ts"].dt.year
    pos = 0
    yrs = 0
    for y in sorted(sub["year"].unique()):
        m = sub["year"] == y
        bm = base["year"] == y
        if m.sum() < 30 or bm.sum() < 30:
            continue
        yrs += 1
        if sub.loc[m, "net_R_m1"].mean() > base.loc[bm, "net_R_m1"].mean():
            pos += 1
    return float(pos / yrs) if yrs else 0.0
