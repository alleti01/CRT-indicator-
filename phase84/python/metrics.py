"""Phase84 metrics and shadow scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_r(df: pd.DataFrame, r_col: str = "net_R") -> dict:
    if df.empty or r_col not in df.columns:
        return {"N": 0}
    rs = df[r_col].astype(float).values
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    eq = np.cumsum(rs)
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    out = {
        "N": int(len(rs)),
        "WinRate": float((rs > 0).mean()),
        "AvgR": float(rs.mean()),
        "PF": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf"),
        "TotalR": float(rs.sum()),
        "MaxDD": float((np.maximum.accumulate(eq) - eq).max()),
        "MedianR": float(np.median(rs)),
    }
    if "exit_reason" in df.columns:
        for reason in ("M0_STOP", "SAME_BAR_STOP_FIRST", "M0_TARGET", "MAX_HOLD_60M"):
            out[f"pct_{reason}"] = float((df["exit_reason"] == reason).mean())
    if "phase72a_direction" in df.columns:
        for d in ("LONG", "SHORT"):
            sub = df.loc[df["phase72a_direction"] == d, r_col].astype(float)
            out[f"{d}_N"] = int(len(sub))
            out[f"{d}_AvgR"] = float(sub.mean()) if len(sub) else 0.0
    return out


def retention_stats(taken_mask: pd.Series) -> dict:
    n = len(taken_mask)
    if n == 0:
        return {"retention_pct": 0.0, "pass_pct": 0.0}
    return {
        "retention_pct": float(taken_mask.mean() * 100),
        "pass_pct": float((~taken_mask).mean() * 100),
    }


def rejected_shadow(rejected: pd.DataFrame, baseline_r_col: str = "baseline_net_R") -> dict:
    return summarize_r(rejected, baseline_r_col)


def random_pass_control(df: pd.DataFrame, mask: pd.Series, seed: int = 42) -> pd.Series:
    rng = np.random.default_rng(seed)
    n_keep = int(mask.sum())
    idx = np.where(mask.values)[0]
    if n_keep == 0:
        return pd.Series(False, index=df.index)
    keep = rng.choice(idx, size=n_keep, replace=False)
    out = pd.Series(False, index=df.index)
    out.iloc[keep] = True
    return out
