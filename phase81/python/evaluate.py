"""Phase81 metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize_trades(df: pd.DataFrame, *, r_col: str = "net_R_m1") -> dict:
    rs = df[r_col].astype(float).values
    rs = rs[np.isfinite(rs)]
    if len(rs) == 0:
        return {"N": 0}
    eq = np.cumsum(rs)
    wins = rs[rs > 0]
    losses = rs[rs <= 0]
    reasons = df.get("exit_reason_m1", pd.Series(dtype=str))
    out = {
        "N": int(len(rs)),
        "WinRate": float((rs > 0).mean()),
        "AvgR": float(rs.mean()),
        "PF": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf"),
        "TotalR": float(rs.sum()),
        "MaxDD": float((np.maximum.accumulate(eq) - eq).max()),
        "MedianR": float(np.median(rs)),
        "MedianHold": float(df["duration_min_m1"].median()) if "duration_min_m1" in df else 0,
        "AvgHold": float(df["duration_min_m1"].mean()) if "duration_min_m1" in df else 0,
        "MFE": float(df["MFE_R_m1"].mean()) if "MFE_R_m1" in df else 0,
        "MAE": float(df["MAE_R_m1"].mean()) if "MAE_R_m1" in df else 0,
        "GrossAvgR": float(df["gross_R_m1"].mean()) if "gross_R_m1" in df else 0,
    }
    if len(reasons):
        n = len(df)
        out["STOP_PCT"] = float(reasons.str.contains("STOP", na=False).mean())
        out["TARGET_PCT"] = float(reasons.str.contains("TARGET", na=False).mean())
        out["TIME_PCT"] = float(reasons.str.contains("HOLD|TIME", na=False).mean())
    return out
