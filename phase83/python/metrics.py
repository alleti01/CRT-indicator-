"""Summary metrics for Phase83."""
from __future__ import annotations

import numpy as np
import pandas as pd


def summarize(df: pd.DataFrame, r_col: str = "net_r") -> dict:
    if df is None or len(df) == 0:
        return {"N": 0}
    rs = df[r_col].astype(float).to_numpy()
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
        "GrossAvgR": float(df["gross_r"].mean()) if "gross_r" in df else float(rs.mean()),
        "LONG": int((df["direction"] == "LONG").sum()) if "direction" in df else 0,
        "SHORT": int((df["direction"] == "SHORT").sum()) if "direction" in df else 0,
    }
    for col, key in (("mfe_15", "MFE15"), ("mae_15", "MAE15"), ("mfe_30", "MFE30"), ("mae_30", "MAE30")):
        if col in df:
            out[key] = float(pd.to_numeric(df[col], errors="coerce").mean())
    return out


def split_by_dates(df: pd.DataFrame, train_dates, valid_dates, test_dates) -> dict[str, pd.DataFrame]:
    return {
        "train": df[df["date"].isin(train_dates)],
        "validation": df[df["date"].isin(valid_dates)],
        "test": df[df["date"].isin(test_dates)],
    }


def year_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y, g in df.groupby("year"):
        s = summarize(g)
        s["year"] = int(y)
        rows.append(s)
    return pd.DataFrame(rows)


def side_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for side in ("LONG", "SHORT", "ALL"):
        g = df if side == "ALL" else df[df["direction"] == side]
        s = summarize(g)
        s["side"] = side
        rows.append(s)
    return pd.DataFrame(rows)


def bucket_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for b, g in df.groupby("time_bucket"):
        s = summarize(g)
        s["time_bucket"] = b
        rows.append(s)
    return pd.DataFrame(rows)
