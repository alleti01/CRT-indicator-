"""Phase82 metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(df: pd.DataFrame, r_col: str = "net_R") -> dict:
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
        "MedianHold": float(df["duration_min"].median()) if "duration_min" in df else 0,
        "AvgHold": float(df["duration_min"].mean()) if "duration_min" in df else 0,
        "MFE": float(df["MFE_R"].mean()) if "MFE_R" in df else 0,
        "MAE": float(df["MAE_R"].mean()) if "MAE_R" in df else 0,
        "GrossAvgR": float(df["gross_R"].mean()) if "gross_R" in df else float(rs.mean()),
    }
    if "exit_reason" in df.columns:
        er = df["exit_reason"].astype(str)
        out["STOP_PCT"] = float(er.str.contains("STOP", na=False).mean())
        out["TARGET_PCT"] = float(er.str.contains("TARGET", na=False).mean())
        out["TIME_PCT"] = float(er.str.contains("HOLD|TIME", na=False).mean())
    return out


def side_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = [summarize(df)]
    rows[0]["side"] = "COMBINED"
    for side in ("LONG", "SHORT"):
        sub = df[df["direction"] == side]
        s = summarize(sub)
        s["side"] = side
        rows.append(s)
    return pd.DataFrame(rows)
