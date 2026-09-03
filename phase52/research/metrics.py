"""Performance metrics for Phase52."""

from __future__ import annotations

import numpy as np
import pandas as pd


def pf(rs: pd.Series) -> float:
    wins = rs[rs > 0].sum()
    losses = rs[rs <= 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else np.nan
    return float(wins / abs(losses))


def max_dd(rs: pd.Series) -> float:
    if rs.empty:
        return np.nan
    eq = rs.cumsum()
    peak = eq.cummax()
    return float((peak - eq).max())


def summarize_trades(df: pd.DataFrame, r_col: str = "net_R") -> dict:
    if df.empty or r_col not in df.columns:
        return {"N": 0}
    rs = df[r_col].astype(float)
    days = max((df["entry_timestamp"].max() - df["entry_timestamp"].min()).days, 1)
    out = {
        "N": len(df),
        "trades_per_day": len(df) / days,
        "AvgR": float(rs.mean()),
        "median_R": float(rs.median()),
        "PF": pf(rs),
        "TotalR": float(rs.sum()),
        "MaxDD": max_dd(rs),
        "win_rate": float((rs > 0).mean()),
        "MAE": float(df["MAE_R"].mean()) if "MAE_R" in df.columns else np.nan,
        "MFE": float(df["MFE_R"].mean()) if "MFE_R" in df.columns else np.nan,
    }
    for side in ("LONG", "SHORT"):
        sub = df.loc[df["direction"] == side]
        if len(sub):
            out[f"{side}_N"] = len(sub)
            out[f"{side}_AvgR"] = float(sub[r_col].mean())
            out[f"{side}_PF"] = pf(sub[r_col])
        else:
            out[f"{side}_N"] = 0
            out[f"{side}_AvgR"] = np.nan
            out[f"{side}_PF"] = np.nan
    return out


def primary_table_row(model: str, family: str, ctx: str, m: dict, extras: dict | None = None) -> dict:
    row = {
        "MODEL": model,
        "FAMILY": family,
        "CONTEXT": ctx,
        "N": m.get("N", 0),
        "TRADES/DAY": round(m.get("trades_per_day", 0), 3),
        "AVGR": round(m.get("AvgR", np.nan), 4) if m.get("N", 0) else np.nan,
        "PF": round(m.get("PF", np.nan), 3) if m.get("N", 0) else np.nan,
        "TOTALR": round(m.get("TotalR", np.nan), 2) if m.get("N", 0) else np.nan,
        "MAXDD": round(m.get("MaxDD", np.nan), 3) if m.get("N", 0) else np.nan,
        "WINRATE": round(m.get("win_rate", np.nan), 3) if m.get("N", 0) else np.nan,
        "MAE": round(m.get("MAE", np.nan), 3) if m.get("N", 0) else np.nan,
        "MFE": round(m.get("MFE", np.nan), 3) if m.get("N", 0) else np.nan,
        "LONG AVGR": round(m.get("LONG_AvgR", np.nan), 4),
        "SHORT AVGR": round(m.get("SHORT_AvgR", np.nan), 4),
    }
    if extras:
        row.update(extras)
    return row
