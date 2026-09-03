"""Analysis tables for Phase 46 VWAP research."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance


def _perf(df: pd.DataFrame, col: str = "B0_net_R") -> dict:
    if df.empty:
        return {"N": 0, "WinRate": 0.0, "AvgR": 0.0, "TotalR": 0.0, "PF": 0.0, "MaxDD": 0.0}
    return performance(df, col=col)


def summary_row(model: str, df: pd.DataFrame, filled: pd.Series, col: str = "B0_net_R", delay_col: str = "B0_delay_min") -> dict:
    sub = df.loc[filled]
    p = _perf(sub, col)
    wd = float(sub["B0_wrong_direction"].mean()) if "B0_wrong_direction" in sub.columns and len(sub) else np.nan
    if "V_wrong_direction" in sub.columns and col.startswith("V"):
        wd = float(sub["V_wrong_direction"].mean()) if len(sub) else np.nan
    mae = float(sub["B0_MAE_R"].mean()) if "B0_MAE_R" in sub.columns and col == "B0_net_R" else (
        float(sub["V_MAE_R"].mean()) if "V_MAE_R" in sub.columns else np.nan
    )
    mfe = float(sub["B0_MFE_R"].mean()) if "B0_MFE_R" in sub.columns and col == "B0_net_R" else (
        float(sub["V_MFE_R"].mean()) if "V_MFE_R" in sub.columns else np.nan
    )
    delay = float(sub[delay_col].mean()) if delay_col in sub.columns and len(sub) else np.nan
    if col.startswith("V") and "V_delay_min" in sub.columns:
        delay = float(sub["V_delay_min"].mean()) if len(sub) else np.nan
    n_base = len(df)
    return {
        "MODEL": model,
        "N": p["N"],
        "RETENTION": p["N"] / n_base if n_base else 0.0,
        "AvgR": p["AvgR"],
        "PF": p["PF"],
        "TotalR": p["TotalR"],
        "MaxDD": p["MaxDD"],
        "MAE": mae,
        "MFE": mfe,
        "WrongDir": wd,
        "EntryDelay": delay,
    }


def variant_summary_table(b0: pd.DataFrame, variants: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = [summary_row("B0_Phase44+B1", b0, b0["b0_filled"])]
    names = {"V1": "V1_Side", "V2": "V2_Reclaim", "V3": "V3_Slope", "V4": "V4_Distance", "V5": "V5_Retest"}
    for key, vdf in variants.items():
        if vdf.empty:
            continue
        rows.append(summary_row(names.get(key, key), vdf, vdf["V_filled"], col="V_net_R"))
    return pd.DataFrame(rows)


def incremental_table(summary: pd.DataFrame) -> pd.DataFrame:
    base = summary.loc[summary["MODEL"] == "B0_Phase44+B1"].iloc[0]
    rows = []
    for _, row in summary.iterrows():
        if row["MODEL"] == "B0_Phase44+B1":
            continue
        rows.append(
            {
                "MODEL": row["MODEL"],
                "RETENTION": row["RETENTION"],
                "dAvgR": row["AvgR"] - base["AvgR"],
                "dPF": row["PF"] - base["PF"],
                "dTotalR": row["TotalR"] - base["TotalR"],
                "dMaxDD": row["MaxDD"] - base["MaxDD"],
                "dMAE": base["MAE"] - row["MAE"],
                "dMFE": row["MFE"] - base["MFE"],
                "dWrongDir": base["WrongDir"] - row["WrongDir"],
                "dDelay": row["EntryDelay"] - base["EntryDelay"],
            }
        )
    return pd.DataFrame(rows)


def descriptive_vwap_buckets(trades: pd.DataFrame) -> pd.DataFrame:
    b0 = trades.loc[trades["b0_filled"]].copy()
    if b0.empty:
        return pd.DataFrame()
    b0["dist_bucket"] = pd.cut(
        b0["abs_vwap_dist_atr"],
        bins=[0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, np.inf],
        labels=["0-0.25", "0.25-0.5", "0.5-0.75", "0.75-1.0", "1.0-1.5", "1.5-2.0", ">2.0"],
    )
    rows = []
    for bucket, sub in b0.groupby("dist_bucket", observed=True):
        p = _perf(sub, "B0_net_R")
        rows.append(
            {
                "bucket": str(bucket),
                "N": p["N"],
                "AvgR": p["AvgR"],
                "MedianR": float(sub["B0_net_R"].median()),
                "PF": p["PF"],
                "WinRate": p["WinRate"],
                "MAE": float(sub["B0_MAE_R"].mean()),
                "MFE": float(sub["B0_MFE_R"].mean()),
                "TotalR": p["TotalR"],
                "wrong_direction_rate": float(sub["B0_wrong_direction"].mean()),
            }
        )
    return pd.DataFrame(rows)


def matched_comparison(b0: pd.DataFrame, vdf: pd.DataFrame, model: str) -> pd.DataFrame:
    m = b0.merge(vdf[["signal_id", "V_filled", "V_net_R", "V_MAE_R", "V_MFE_R", "V_wrong_direction", "V_delay_min"]], on="signal_id", how="inner")
    both = m.loc[m["b0_filled"] & m["V_filled"]]
    rows = []
    if not both.empty:
        rows.append(
            {
                "model": model,
                "segment": "matched",
                "N": len(both),
                "dAvgR": float((both["V_net_R"] - both["B0_net_R"]).mean()),
                "dPF": _perf(both, "V_net_R")["PF"] - _perf(both, "B0_net_R")["PF"],
                "dMAE": float(both["B0_MAE_R"].mean() - both["V_MAE_R"].mean()),
                "dMFE": float(both["V_MFE_R"].mean() - both["B0_MFE_R"].mean()),
                "dWrongDir": float(both["B0_wrong_direction"].mean() - both["V_wrong_direction"].mean()),
                "dDelay": float(both["V_delay_min"].mean() - both["B0_delay_min"].mean()),
            }
        )
    rej = m.loc[m["b0_filled"] & ~m["V_filled"]]
    if not rej.empty:
        p = _perf(rej, "B0_net_R")
        rows.append(
            {
                "model": model,
                "segment": "rejected_by_vwap",
                "N": p["N"],
                "dAvgR": p["AvgR"],
                "dPF": p["PF"],
                "dMAE": float(rej["B0_MAE_R"].mean()),
                "dMFE": float(rej["B0_MFE_R"].mean()),
                "dWrongDir": float(rej["B0_wrong_direction"].mean()),
                "dDelay": np.nan,
            }
        )
    return pd.DataFrame(rows)


def stratified_results(b0: pd.DataFrame, vdf: pd.DataFrame, model: str) -> pd.DataFrame:
    rows = []
    m = b0.merge(vdf[["signal_id", "V_filled", "V_net_R"]], on="signal_id", how="left")
    m["V_filled"] = m["V_filled"].fillna(False)

    def _add(seg: str, sub: pd.DataFrame):
        bf = sub.loc[sub["b0_filled"]]
        vf = sub.loc[sub["V_filled"]]
        pb, pv = _perf(bf, "B0_net_R"), _perf(vf, "V_net_R")
        rows.append({"model": model, "segment": seg, "B0_N": pb["N"], "V_N": pv["N"], "B0_AvgR": pb["AvgR"], "V_AvgR": pv["AvgR"], "B0_PF": pb["PF"], "V_PF": pv["PF"]})

    for st in ("L", "S"):
        _add(f"dir_{st}", m.loc[m["signal_type"] == st])
    for tier in ("A+", "A", "B"):
        _add(f"tier_{tier}", m.loc[m["confidence"] == tier])
    for st in ("RL", "RS"):
        _add(f"setup_{st}", m.loc[m["signal_type"] == st])
    m["year"] = pd.to_datetime(m["marker_bar_timestamp"]).dt.year
    for year in (2024, 2025, 2026):
        _add(f"year_{year}", m.loc[m["year"] == year])
    return pd.DataFrame(rows)


def robustness_cost(vdf: pd.DataFrame, model: str) -> pd.DataFrame:
    sub = vdf.loc[vdf["V_filled"]].copy()
    if sub.empty:
        return pd.DataFrame()
    sub["realized_R"] = sub["V_net_R"] + 0  # already net; re-apply via gross if available
    if "B0_gross_R" in sub.columns:
        sub["realized_R"] = sub.get("V_gross_R", sub["V_net_R"])
    rows = []
    for mult in (1.0, 1.5, 2.0):
        if mult == 1.0:
            p = _perf(sub, "V_net_R")
        else:
            tmp = sub.copy()
            tmp["entry_price"] = tmp.get("V_entry_price", tmp["B0_entry_price"])
            tmp["stop_price"] = tmp["stop"]
            tmp["realized_R"] = tmp["V_net_R"]  # approximate stress
            net = apply_costs(tmp.assign(result_R=tmp["realized_R"]), multiplier=mult, col="result_R")
            tmp["net_R"] = net
            p = _perf(tmp, "net_R")
        p["cost_multiplier"] = mult
        p["model"] = model
        rows.append(p)
    return pd.DataFrame(rows)


def ex_top1pct(vdf: pd.DataFrame, model: str) -> pd.DataFrame:
    sub = vdf.loc[vdf["V_filled"]].sort_values("V_net_R", ascending=False)
    if sub.empty:
        return pd.DataFrame()
    n1 = max(1, int(np.ceil(len(sub) * 0.01)))
    return pd.DataFrame(
        [
            {"model": model, "segment": "FULL", **_perf(sub, "V_net_R")},
            {"model": model, "segment": "exclude_top1pct", **_perf(sub.iloc[n1:], "V_net_R")},
        ]
    )
