"""Analysis tables for Phase 48."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance


def summarize_trades(df: pd.DataFrame, model: str) -> dict:
    if df.empty:
        return {"MODEL": model, "N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0, "WinRate": 0.0, "MAE": np.nan, "MFE": np.nan, "MFE_Capture": np.nan, "AvgHold": np.nan}
    p = performance(df, col="net_R")
    return {
        "MODEL": model,
        "N": p["N"],
        "AvgR": p["AvgR"],
        "PF": p["PF"],
        "TotalR": p["TotalR"],
        "MaxDD": p["MaxDD"],
        "WinRate": p["WinRate"],
        "MAE": float(df["MAE_R"].mean()),
        "MFE": float(df["MFE_R"].mean()),
        "MFE_Capture": float(df["mfe_capture"].mean()) if "mfe_capture" in df.columns else np.nan,
        "AvgHold": float(df["hold_bars"].mean()) if "hold_bars" in df.columns else np.nan,
    }


def family_summary(m0: pd.DataFrame, wf: pd.DataFrame) -> pd.DataFrame:
    rows = [summarize_trades(m0, "M0_Control")]
    for fam in wf["family"].unique() if not wf.empty else []:
        sub = wf.loc[wf["family"] == fam]
        rows.append(summarize_trades(sub, fam))
    return pd.DataFrame(rows)


def incremental_table(summary: pd.DataFrame) -> pd.DataFrame:
    base = summary.loc[summary["MODEL"] == "M0_Control"].iloc[0]
    rows = []
    for _, row in summary.iterrows():
        if row["MODEL"] == "M0_Control":
            continue
        rows.append({
            "MODEL": row["MODEL"],
            "dAvgR": row["AvgR"] - base["AvgR"],
            "dPF": row["PF"] - base["PF"],
            "dTotalR": row["TotalR"] - base["TotalR"],
            "dMaxDD": row["MaxDD"] - base["MaxDD"],
            "dWinRate": row["WinRate"] - base["WinRate"],
            "dMFE_Capture": row["MFE_Capture"] - base["MFE_Capture"] if np.isfinite(row["MFE_Capture"]) else np.nan,
            "dAvgHold": row["AvgHold"] - base["AvgHold"] if np.isfinite(row["AvgHold"]) else np.nan,
        })
    return pd.DataFrame(rows)


def matched_incremental(m0: pd.DataFrame, variant: pd.DataFrame) -> dict:
    m = m0.merge(variant[["signal_id", "net_R", "MAE_R", "MFE_R", "hold_bars", "mfe_capture"]], on="signal_id", suffixes=("_m0", "_v"))
    if m.empty:
        return {}
    return {
        "N": len(m),
        "dAvgR": float((m["net_R_v"] - m["net_R_m0"]).mean()),
        "dMAE": float((m["MAE_R_m0"] - m["MAE_R_v"]).mean()),
        "dMFE_Capture": float((m["mfe_capture_v"] - m["mfe_capture_m0"]).mean()) if "mfe_capture_v" in m.columns else np.nan,
        "dHold": float((m["hold_bars_v"] - m["hold_bars_m0"]).mean()),
    }


def stratified_results(wf: pd.DataFrame, entries: pd.DataFrame, col: str, vals: tuple) -> pd.DataFrame:
    rows = []
    meta = entries[["signal_id", col]].drop_duplicates()
    wf2 = wf.merge(meta, on="signal_id", how="left")
    for fam in wf2["family"].unique():
        for v in vals:
            sub = wf2.loc[(wf2["family"] == fam) & (wf2[col] == v)]
            p = performance(sub, col="net_R") if not sub.empty else {"N": 0, "AvgR": 0.0}
            rows.append({"family": fam, "segment": v, "N": p["N"], "AvgR": p["AvgR"]})
    return pd.DataFrame(rows)


def yearly_results(wf: pd.DataFrame, entries: pd.DataFrame) -> pd.DataFrame:
    e = entries.copy()
    e["year"] = pd.to_datetime(e["entry_timestamp"]).dt.year
    wf2 = wf.merge(e[["signal_id", "year"]], on="signal_id")
    rows = []
    for year in (2024, 2025, 2026):
        for fam in wf2["family"].unique():
            sub = wf2.loc[(wf2["year"] == year) & (wf2["family"] == fam)]
            p = performance(sub, col="net_R") if not sub.empty else {"N": 0, "AvgR": 0.0}
            rows.append({"year": year, "family": fam, "N": p["N"], "AvgR": p["AvgR"]})
    return pd.DataFrame(rows)


def exit_efficiency(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    win = df.loc[df["net_R"] > 0]
    lose = df.loc[df["net_R"] <= 0]
    return pd.DataFrame([{
        "N": len(df),
        "exit_efficiency_win": float((win["net_R"] / win["MFE_R"].replace(0, np.nan)).mean()) if len(win) else np.nan,
        "giveback_mean": float((df["MFE_R"] - df["net_R"]).mean()),
        "loss_efficiency": float((lose["net_R"] / lose["MAE_R"].replace(0, np.nan)).mean()) if len(lose) else np.nan,
    }])


def robustness(df: pd.DataFrame, model: str) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        t = df.copy()
        if mult == 1.0:
            p = performance(t, col="net_R")
        else:
            t["entry_price"] = t.get("entry_price", np.nan)
            t["stop_price"] = t.get("initial_stop", np.nan)
            t["result_R"] = t["net_R"]
            t["net_R_adj"] = apply_costs(t.assign(entry_price=t["entry_price"], stop_price=t["stop_price"]), multiplier=mult, col="result_R")
            p = performance(t, col="net_R_adj")
        p["cost_multiplier"] = mult
        p["model"] = model
        rows.append(p)
    return pd.DataFrame(rows)
